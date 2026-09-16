module infer.ease;

import std.stdio : writeln;
import std.string : strip, toLower;
import std.array : join;
import std.algorithm : min;
import std.conv : to;
import std.json : JSONValue;
import std.math : sqrt;

import intuit;
import infer.config;
import akashi.page : Page;
import akashi.text.ast : Document, Node;

private:

OpenAI _client;
string _lastEndpoint;

OpenAI client()
{
    if (_client is null || _lastEndpoint != config.endpoint)
    {
        _client = new OpenAI(config.endpoint);
        _lastEndpoint = config.endpoint;
        _client.available();
    }
    return _client;
}

immutable string[] excluded = [
    "references", "external links", "further reading", "see also",
    "notes", "bibliography", "sources", "footnotes",
    "common names", "reagent results", "media", "literature",
    "experience reports", "gallery", "navigation",
];

enum minContentLength = 50;

bool isExcluded(string heading)
{
    string lower = heading.toLower;
    foreach (ex; excluded)
    {
        if (lower == ex)
            return true;
    }
    return false;
}

float cosineSimilarity(float[] a, float[] b)
{
    if (a.length == 0 || a.length != b.length)
        return 0.0f;

    float dot;
    float na;
    float nb;
    foreach (i; 0 .. a.length)
    {
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    if (na == 0 || nb == 0)
        return 0.0f;

    return dot / (sqrt(na) * sqrt(nb));
}

struct SourceSection
{
    string heading;
    string content;
    int level;
    string origin;
    float[] embedding;
    float[] contentEmbedding;
}

Section[] pageSections(Page page)
{
    Section[] ret;

    Document doc = page.document();
    Node[] nodes = doc.sections();
    foreach (ref node; nodes)
        ret ~= Section(node.text, doc.extractText(node), cast(int) node.level);

    return ret;
}

SourceSection[] extractSections(Page[] pages)
{
    SourceSection[] all;

    foreach (page; pages)
    {
        string raw = page.raw;
        if (raw is null || raw.length == 0)
            continue;

        writeln("[Ease] Processing page: ", page.title, " (", page.source, ")");

        string preamble = page.preamble;
        if (preamble.length > minContentLength)
        {
            all ~= SourceSection("Introduction", preamble, 2, page.source);
            writeln("[Ease]   + Introduction (", preamble.length, " chars)");
        }

        Section[] sections = pageSections(page);

        string currentParent;
        string currentContent;
        int subCount;

        void flushParent()
        {
            if (currentParent.length == 0)
                return;
            if (currentContent.length >= minContentLength && !isExcluded(currentParent))
            {
                all ~= SourceSection(currentParent, currentContent, 2, page.source);
                writeln("[Ease]   + '", currentParent, "' (",
                    currentContent.length, " chars, ", subCount, " subsections folded)");
            }
            else if (isExcluded(currentParent))
                writeln("[Ease]   - SKIP '", currentParent, "' (excluded)");
            else
                writeln("[Ease]   - SKIP '", currentParent,
                    "' (too short: ", currentContent.length, ")");
            currentParent = null;
            currentContent = null;
            subCount = 0;
        }

        foreach (sec; sections)
        {
            if (sec.level <= 2)
            {
                flushParent();
                currentParent = sec.heading;
                currentContent = sec.content;
                subCount = 0;
            }
            else
            {
                if (currentParent.length > 0)
                {
                    if (isExcluded(sec.heading))
                        continue;
                    currentContent ~= "\n\n==="~sec.heading~"===\n"~sec.content;
                    subCount++;
                }
                else
                {
                    if (sec.content.length >= minContentLength
                        && !isExcluded(sec.heading))
                    {
                        all ~= SourceSection(sec.heading, sec.content, 2, page.source);
                        writeln("[Ease]   + '", sec.heading,
                            "' (", sec.content.length, " chars, orphan)");
                    }
                }
            }
        }
        flushParent();
    }

    return all;
}

void embedAll(SourceSection[] sections)
{
    if (sections.length == 0)
        return;

    string[] texts;
    foreach (ref s; sections)
    {
        texts ~= s.heading.toLower;
        texts ~= s.content[0..min($, 300)];
    }

    try
    {
        auto embeddings = client.embeddings!float(config.embedModel, texts);
        foreach (i, ref s; sections)
        {
            s.embedding = embeddings[i * 2].value;
            s.contentEmbedding = embeddings[i * 2 + 1].value;
        }
    }
    catch (Exception e)
    {
        writeln("[Ease] Batch embedding failed: ", e.msg);
    }
}

SourceSection[][] groupSections(SourceSection[] sections)
{
    if (sections.length == 0)
        return [];

    float threshold = config.groupingThreshold;

    if (sections[0].embedding.length == 0)
        return groupByHeading(sections);

    bool[] assigned = new bool[sections.length];
    SourceSection[][] groups;

    foreach (i; 0..sections.length)
    {
        if (assigned[i])
            continue;

        SourceSection[] group;
        group ~= sections[i];
        assigned[i] = true;

        foreach (j; i + 1..sections.length)
        {
            if (assigned[j])
                continue;

            if (sections[i].embedding.length > 0 && sections[j].embedding.length > 0)
            {
                float sim = cosineSimilarity(sections[i].embedding, sections[j].embedding);
                if (sim > threshold)
                {
                    group ~= sections[j];
                    assigned[j] = true;
                }
            }
        }

        groups ~= group;
    }

    return groups;
}

SourceSection[][] groupByHeading(SourceSection[] sections)
{
    string[] seen;
    SourceSection[][string] byHeading;

    foreach (ref s; sections)
    {
        string key = s.heading.toLower;
        if (key !in byHeading)
        {
            seen ~= key;
            byHeading[key] = [];
        }
        byHeading[key] ~= s;
    }

    SourceSection[][] groups;
    foreach (key; seen)
        groups ~= byHeading[key];
    return groups;
}

Section resolveGroup(SourceSection[] group)
{
    string heading = group[0].heading;
    int level = group[0].level;

    if (group.length == 1)
        return Section(heading, group[0].content, level);

    bool allSimilar = true;
    if (group[0].contentEmbedding.length > 0)
    {
        foreach (i; 1..group.length)
        {
            if (group[i].contentEmbedding.length == 0)
            {
                allSimilar = false;
                break;
            }
            float sim = cosineSimilarity(
                group[0].contentEmbedding, group[i].contentEmbedding);
            if (sim < config.dedupeThreshold)
            {
                allSimilar = false;
                break;
            }
        }
    }
    else
        allSimilar = false;

    if (allSimilar)
    {
        writeln("[Ease]   -> Near-duplicate, picking longest");
        SourceSection best = group[0];
        foreach (i; 1..group.length)
        {
            if (group[i].content.length > best.content.length)
                best = group[i];
        }
        return Section(heading, best.content, level);
    }

    return mergeViaLLM(heading, level, group);
}

Section mergeViaLLM(string heading, int level, SourceSection[] group)
{
    string[] parts;
    int totalLen;
    foreach (ref s; group)
    {
        int allowed = config.maxMergeChars / cast(int) group.length;
        string text = s.content.length > allowed
            ? s.content[0..allowed] : s.content;
        parts ~= "["~s.origin~"]\n"~text;
        totalLen += cast(int) text.length;
    }

    string combined = parts.join("\n\n---\n\n");

    string prompt = "Merge these texts about \""~heading
       ~"\" into one cohesive section. "
       ~"Preserve ALL facts from every source. "
       ~"No headings, no citations, encyclopedic prose only.\n\n"
       ~combined;

    try
    {
        ModelConfig model = client.config(config.chatModel);
        model.maxTokens = 2048;
        model.temperature = 0.2;

        JSONValue messages = JSONValue.emptyArray;

        JSONValue sysMsg = JSONValue.emptyObject;
        sysMsg["role"] = JSONValue("system");
        sysMsg["content"] = JSONValue(
            "Merge encyclopedia sections preserving all facts. "
           ~"Output only merged text. /no_think");
        messages.array ~= sysMsg;

        JSONValue userMsg = JSONValue.emptyObject;
        userMsg["role"] = JSONValue("user");
        userMsg["content"] = JSONValue(prompt);
        messages.array ~= userMsg;

        writeln("[Ease]   -> LLM merge (", totalLen, " chars input)");
        Completion completion = client.completions(config.chatModel, messages);
        string merged = completion.choices[0].text;

        if (merged.length > 0)
        {
            writeln("[Ease]   -> LLM produced ", merged.length, " chars");
            return Section(heading, merged.strip, level);
        }
    }
    catch (Exception e)
    {
        writeln("[Ease]   -> LLM merge failed: ", e.msg);
    }

    string[] raw;
    foreach (ref s; group)
        raw ~= s.content;
    return Section(heading, raw.join("\n\n"), level);
}

public:

struct Section
{
    string heading;
    string content;
    int level;
}

alias SectionCallback = void delegate(size_t index, Section sec);
alias HeadingsCallback = void delegate(string[] headings);

void ease(
    string compoundName, 
    HeadingsCallback onHeadings,
    SectionCallback onSection,
    void delegate() onDone,
    Page[] pages...
)
{
    writeln("[Ease] Streaming ease for: ", compoundName,
        " from ", pages.length, " pages");

    SourceSection[] allSections = extractSections(pages);
    writeln("[Ease] Extracted ", allSections.length, " sections");

    if (allSections.length == 0)
    {
        if (onHeadings !is null) onHeadings([]);
        if (onDone !is null) onDone();
        return;
    }

    embedAll(allSections);

    SourceSection[][] groups = groupSections(allSections);
    writeln("[Ease] Formed ", groups.length, " groups");

    string[] headings;
    foreach (group; groups)
        headings ~= group[0].heading;
    if (onHeadings !is null) onHeadings(headings);

    foreach (i, group; groups)
    {
        string sources;
        foreach (ref s; group)
            sources ~= s.origin~" ";
        writeln("[Ease] Resolving ", i + 1, "/", groups.length,
            ": '", group[0].heading, "' (", group.length,
            " sources: ", sources.strip, ")");

        Section sec = resolveGroup(group);
        writeln("[Ease]   => '", sec.heading, "' (", sec.content.length, " chars)");
        onSection(i, sec);
    }

    writeln("[Ease] Streaming complete");
    if (onDone !is null) onDone();
}
