module gui.article.view;

import std.conv : to;
import std.stdio : writeln;
import std.regex : ctRegex, replaceAll;
import std.array : replace;
import std.string : toLower, strip, indexOf, startsWith;
import std.algorithm : canFind;
import std.uni : toUpper;
import core.thread : Thread;

import gtk.box;
import gtk.label;
import gtk.button;
import gtk.scrolled_window;
import gtk.overlay;
import gtk.gesture_click;
import gtk.event_controller_motion;
import gtk.types : Orientation, Align, PolicyType;
import gtk.widget : Widget;

import gui.article.infobox;
import gui.article.expander;
import gui.article.reports : Reports;
import gui.article.render : renderPage, renderNode;
import gui.loading : makeLoadingDots;
import gui.window : ChemicaWindow;
import gui.conformer.view;

import akashi.pubchem;
import akashi.page : Page, Section, resolvePage;
import akashi.text.ast : Document, Node, NodeType;
import akashi.psychonaut : DosageResult;
import infer.ease : ease, SectionCallback, HeadingsCallback;
import infer.resolve : extractCompoundNames;
import infer.config : config;


class ArticleView : Overlay
{
private:
    ScrolledWindow scroller;
    Box root;
    Box content;

    MoleculeView moleculeView;
    Overlay screenOverlay;

    Box synthesisBody;
    Compound compound;
    string[] navHistory;
    Page[] cachedPages;

    bool inReportView;
    Box reportView;

public:
    Infobox infobox;
    void delegate(string compoundName) onCompoundNavigate;

    this()
    {
        super();
        hexpand = true;
        vexpand = true;

        scroller = new ScrolledWindow();
        scroller.addCssClass("article-scroll");
        scroller.hexpand = true;
        scroller.vexpand = true;
        scroller.setPolicy(PolicyType.Never, PolicyType.Automatic);

        root = new Box(Orientation.Horizontal, 0);
        root.addCssClass("article");
        root.hexpand = true;
        root.valign = Align.Start;

        content = new Box(Orientation.Vertical, 0);
        content.addCssClass("article-content");
        content.hexpand = true;
        content.vexpand = true;
        root.append(content);

        moleculeView = new MoleculeView();
        GestureClick viewerClick = new GestureClick();
        viewerClick.connectReleased(&onViewerClicked);
        moleculeView.addController(viewerClick);

        scroller.setChild(root);
        setChild(scroller);

        buildOverlay();
    }

    void fromCompound(Compound compound, bool pushHistory = true)
    {
        if (pushHistory && this.compound !is null)
            navHistory ~= this.compound.name;

        clearArticle();
        moleculeView.setCompound(compound);

        Box nav = new Box(Orientation.Horizontal, 0);
        nav.addCssClass("article-nav");
        nav.hexpand = true;
        nav.halign = Align.Fill;
        nav.valign = Align.Start;

        Button backBtn = new Button();
        backBtn.iconName = "go-previous-symbolic";
        backBtn.tooltipText = "Back";
        backBtn.addCssClass("nav-home-button");
        backBtn.addCssClass("nav-back-button");
        backBtn.connectClicked(&onBackClicked);
        backBtn.halign = Align.Start;
        backBtn.valign = Align.Center;
        nav.append(backBtn);

        Label navTitle = new Label(compound.name);
        navTitle.addCssClass("article-nav-title");
        navTitle.halign = Align.Start;
        navTitle.hexpand = true;
        navTitle.xalign = 0;
        navTitle.marginStart = 8;
        nav.append(navTitle);

        Button homeBtn = new Button();
        homeBtn.iconName = "go-home-symbolic";
        homeBtn.tooltipText = "Back to home";
        homeBtn.addCssClass("nav-home-button");
        homeBtn.connectClicked(() {
            navHistory = null;
            ChemicaWindow.instance.goHome();
        });
        homeBtn.halign = Align.End;
        homeBtn.valign = Align.Center;
        nav.append(homeBtn);
        content.append(nav);

        this.compound = compound;

        synthesisBody = new Box(Orientation.Vertical, 0);
        synthesisBody.addCssClass("article-content");
        synthesisBody.hexpand = true;
        Label loading = new Label("Synthesizing article...");
        loading.addCssClass("report-body-text");
        loading.halign = Align.Start;
        synthesisBody.append(loading);
        content.append(synthesisBody);

        Thread synthThread = new Thread(&fetchAndSynthesize);
        synthThread.start();

        Reports reports = new Reports(compound.name);
        reports.onReportSelected = &fromReport;
        content.append(reports);

        infobox = new Infobox(moleculeView, compound);
        root.append(infobox);
    }

    void onBackClicked()
    {
        if (navHistory.length > 0)
        {
            string prev = navHistory[$ - 1];
            navHistory = navHistory[0..$ - 1];
            if (onCompoundNavigate !is null)
                onCompoundNavigate(prev);
        }
        else
            ChemicaWindow.instance.goHome();
    }

    Page[] pages()
    {
        if (cachedPages !is null)
            return cachedPages;
        cachedPages = fetchPages();
        return cachedPages;
    }

    void clearArticle()
    {
        if (inReportView)
            hideReport();

        if (infobox !is null)
        {
            infobox.subject.remove(moleculeView);
            root.remove(infobox);
            infobox = null;
        }

        Widget child = content.getFirstChild();
        while (child !is null)
        {
            Widget next = child.getNextSibling();
            content.remove(child);
            child = next;
        }

        compound = null;
        cachedPages = null;
        synthesisBody = null;
        moleculeView.setCompound(null);
    }

private:
    static bool isExcludedHeading(string heading)
    {
        immutable string[] excluded = [
            "references", "external links", "further reading",
            "see also", "notes", "bibliography", "sources",
            "footnotes", "gallery", "navigation",
        ];
        string lower = heading.toLower;
        foreach (ex; excluded)
            if (lower == ex) return true;
        return false;
    }

    Page[] fetchPages()
    {
        return resolvePage(compound);
    }

    Label makeTextLabel(string text, bool markup = false)
    {
        Label lbl = new Label(text);
        lbl.addCssClass("report-body-text");
        lbl.halign = Align.Start;
        lbl.xalign = 0;
        lbl.wrap = true;
        lbl.hexpand = true;
        lbl.selectable = true;
        if (markup)
        {
            lbl.useMarkup = true;
            lbl.connectActivateLink(&onLinkActivated);
        }
        return lbl;
    }

    void populateSectionContent(Expander exp, Section sec)
    {
        if (sec.content.length == 0)
        {
            Label empty = new Label("No content.");
            empty.addCssClass("expander-detail");
            empty.halign = Align.Start;
            exp.addContent(empty);
            return;
        }

        string markup = linkifyUrls(sec.content);
        Label lbl = makeTextLabel(markup, true);
        exp.addContent(lbl);
        resolveCompoundLinks(lbl, sec.content);
    }

    void populateFromAST(Expander exp, Page page, ref const Node secNode)
    {
        Document doc = page.document();
        if (doc.nodes.length == 0 || !secNode.hasChildren)
        {
            Label empty = new Label("No content.");
            empty.addCssClass("expander-detail");
            empty.halign = Align.Start;
            exp.addContent(empty);
            return;
        }

        // Recursively render section children, handling nested sections.
        renderSectionChildren(doc, secNode, exp.content);
    }

    void renderSectionChildren(ref Document doc, ref const Node sec, Box container)
    {
        uint ci = sec.childStart;
        while (ci < sec.childEnd)
        {
            if (doc.nodes[ci].type == NodeType.Section)
            {
                // Subsection: render heading + recurse into children.
                if (doc.nodes[ci].text.length > 0)
                {
                    Label subHead = new Label(doc.nodes[ci].text.toUpper);
                    subHead.addCssClass("article-subheading");
                    subHead.halign = Align.Start;
                    subHead.xalign = 0;
                    container.append(subHead);
                }
                if (doc.nodes[ci].hasChildren)
                    renderSectionChildren(doc, doc.nodes[ci], container);
            }
            else
                renderNode(doc, doc.nodes[ci], container);
            ci = doc.nextSiblingIdx(ci);
        }
    }

    void renderDirect(Page[] pages)
    {
        if (synthesisBody is null)
            return;
        clearSynthesisLoading();

        bool hadIntro;

        foreach (page; pages)
        {
            string raw = page.raw;
            if (raw is null || raw.length == 0)
                continue;

            Document doc = page.document();
            if (doc.nodes.length == 0)
                continue;

            // Render preamble via AST nodes.
            Node[] preambleNodes = doc.preamble();
            if (preambleNodes.length > 0)
            {
                hadIntro = true;
                foreach (ref pn; preambleNodes)
                    renderNode(doc, pn, synthesisBody);
            }

            // Render sections as expanders using the AST.
            foreach (ref secNode; doc.sections())
            {
                string heading = secNode.text;
                if (isExcludedHeading(heading))
                    continue;

                Expander exp = new Expander(heading);
                populateFromAST(exp, page, secNode);
                synthesisBody.append(exp);
            }
        }

        if (!hadIntro && compound !is null)
        {
            string desc = compound.description;
            if (desc.length > 0)
            {
                Label lbl = makeTextLabel(linkifyUrls(desc), true);
                synthesisBody.prepend(lbl);
                resolveCompoundLinks(lbl, desc);
            }
        }
        // Resolve compound links on all AST-rendered labels.
        resolveLinksInContainer(synthesisBody);

        writeln("[ArticleView] Direct render complete");
    }

    void clearSynthesisLoading()
    {
        if (synthesisBody is null)
            return;

        Widget first = synthesisBody.getFirstChild();
        if (first !is null)
            synthesisBody.remove(first);
    }

    void fetchAndSynthesize()
    {
        try
        {
            if (compound is null)
                return;

            writeln("[ArticleView] Starting synthesis for: ", compound.name,
                " sources=", config.enabledSources);

            Page[] allPages = pages();
            writeln("[ArticleView] Fetched ", allPages.length, " pages");

            if (allPages.length == 0)
            {
                if (synthesisBody !is null)
                {
                    clearSynthesisLoading();
                    synthesisBody.append(makeTextLabel("No source pages found."));
                }
                return;
            }

            if (config.enabledSources.length <= 1)
            {
                renderDirect(allPages);
                return;
            }

            Expander[] sectionExpanders;
            size_t[size_t] groupToExpander;
            Box introPlaceholder;
            size_t introGroupIdx = size_t.max;

            ease(compound.name,
                (string[] headings) {
                    if (synthesisBody is null)
                        return;
                        
                    clearSynthesisLoading();

                    bool hasIntro;
                    foreach (h; headings)
                    {
                        if (h.toLower == "introduction")
                        {
                            hasIntro = true;
                            break;
                        }
                    }

                    if (!hasIntro && compound !is null)
                    {
                        string desc = compound.description;
                        if (desc.length > 0)
                        {
                            Label lbl = makeTextLabel(linkifyUrls(desc), true);
                            synthesisBody.prepend(lbl);
                            resolveCompoundLinks(lbl, desc);
                        }
                    }

                    foreach (i, heading; headings)
                    {
                        if (heading.toLower == "introduction")
                        {
                            introGroupIdx = i;
                            introPlaceholder = makeLoadingDots();
                            introPlaceholder.marginStart = 16;
                            introPlaceholder.marginTop = 8;
                            introPlaceholder.marginBottom = 8;
                            synthesisBody.append(introPlaceholder);
                        }
                        else
                        {
                            Expander exp = new Expander("");
                            exp.setLoading(true);
                            synthesisBody.append(exp);
                            groupToExpander[i] = sectionExpanders.length;
                            sectionExpanders ~= exp;
                        }
                    }
                },
                (size_t idx, Section sec) {
                    if (synthesisBody is null)
                        return;

                    if (idx == introGroupIdx)
                    {
                        if (introPlaceholder !is null)
                        {
                            synthesisBody.remove(introPlaceholder);
                            introPlaceholder = null;
                        }
                        if (sec.content.length > 0)
                        {
                            Label lbl = makeTextLabel(
                                linkifyUrls(sec.content), true);
                            synthesisBody.prepend(lbl);
                            resolveCompoundLinks(lbl, sec.content);
                        }
                        return;
                    }

                    size_t* pExpIdx = idx in groupToExpander;
                    if (pExpIdx is null)
                        return;

                    Expander exp = sectionExpanders[*pExpIdx];
                    exp.setTitle(sec.heading);
                    populateSectionContent(exp, sec);
                },
                { writeln("[ArticleView] Synthesis complete"); },
                allPages);
        }
        catch (Exception e)
        {
            writeln("[ArticleView] Synthesis failed: ", e.msg);
            if (synthesisBody !is null)
            {
                clearSynthesisLoading();
                synthesisBody.append(makeTextLabel("Article synthesis failed."));
            }
        }
    }

    void fromReport(Page report)
    {
        inReportView = true;

        // Swap scroller child to report view
        scroller.setChild(null);

        reportView = new Box(Orientation.Vertical, 0);
        reportView.addCssClass("article");
        reportView.hexpand = true;
        reportView.vexpand = true;

        // Report nav bar
        Box rNavBar = new Box(Orientation.Horizontal, 0);
        rNavBar.addCssClass("article-nav");
        rNavBar.hexpand = true;
        rNavBar.halign = Align.Fill;
        rNavBar.valign = Align.Start;

        Button backBtn = new Button();
        backBtn.iconName = "go-previous-symbolic";
        backBtn.tooltipText = "Back to compound";
        backBtn.addCssClass("nav-home-button");
        backBtn.addCssClass("nav-back-button");
        backBtn.connectClicked(&hideReport);
        backBtn.halign = Align.Start;
        backBtn.valign = Align.Center;
        rNavBar.append(backBtn);

        Label reportTitle = new Label(report.title);
        reportTitle.addCssClass("article-nav-title");
        reportTitle.halign = Align.Start;
        reportTitle.hexpand = true;
        reportTitle.xalign = 0;
        reportTitle.wrap = true;
        reportTitle.maxWidthChars = 60;
        reportTitle.marginStart = 8;
        rNavBar.append(reportTitle);

        Button homeBtn = new Button();
        homeBtn.iconName = "go-home-symbolic";
        homeBtn.tooltipText = "Back to home";
        homeBtn.addCssClass("nav-home-button");
        homeBtn.connectClicked(() {
            ChemicaWindow.instance.goHome();
        });
        homeBtn.halign = Align.End;
        homeBtn.valign = Align.Center;
        rNavBar.append(homeBtn);

        reportView.append(rNavBar);

        // Report body container
        Box reportBody = new Box(Orientation.Vertical, 0);
        reportBody.addCssClass("report-body");
        reportBody.hexpand = true;

        Label loadingLabel = new Label("Loading report...");
        loadingLabel.addCssClass("report-body-text");
        loadingLabel.halign = Align.Start;
        reportBody.append(loadingLabel);

        reportView.append(reportBody);
        scroller.setChild(reportView);

        // Fetch and render report in background using AST
        Thread fetchThread = new Thread({
            try
            {
                string raw = report.raw;
                if (raw.length == 0)
                {
                    reportBody.remove(loadingLabel);
                    Label noContent = new Label("No content available.");
                    noContent.addCssClass("report-body-text");
                    noContent.halign = Align.Start;
                    reportBody.append(noContent);
                    return;
                }

                reportBody.remove(loadingLabel);
                renderPage(report, reportBody);
            }
            catch (Exception e)
            {
                reportBody.remove(loadingLabel);
                Label errLabel = new Label("Failed to load report.");
                errLabel.addCssClass("report-body-text");
                errLabel.halign = Align.Start;
                reportBody.append(errLabel);
            }
        });
        fetchThread.start();
    }

    void hideReport()
    {
        inReportView = false;
        scroller.setChild(root);
        reportView = null;
    }

    void buildOverlay()
    {
        screenOverlay = new Overlay();
        screenOverlay.hexpand = true;
        screenOverlay.vexpand = true;
        screenOverlay.visible = false;

        Button closeBtn = new Button();
        closeBtn.iconName = "window-close-symbolic";
        closeBtn.tooltipText = "Close";
        closeBtn.addCssClass("fullscreen-close");
        closeBtn.connectClicked(&onCloseFullscreen);
        closeBtn.widthRequest = 40;
        closeBtn.heightRequest = 40;
        closeBtn.halign = Align.End;
        closeBtn.valign = Align.Start;
        closeBtn.marginTop = 12;
        closeBtn.marginEnd = 12;

        screenOverlay.addOverlay(closeBtn);
        addOverlay(screenOverlay);
    }

    void onCloseFullscreen()
    {
        screenOverlay.setChild(null);
        screenOverlay.visible = false;

        if (infobox !is null)
            infobox.setupMView();
    }

    bool onLinkActivated(string uri)
    {
        if (uri.startsWith("compound:"))
        {
            string name = uri[9..$];
            writeln("[ArticleView] Compound link clicked: ", name);
            if (onCompoundNavigate !is null)
                onCompoundNavigate(name);
            return true;
        }
        return false;
    }

    void resolveCompoundLinks(Label lbl, string plainText)
    {
        try
        {
            string[] names = extractCompoundNames(plainText);
            if (names.length == 0)
                return;

            writeln("[ArticleView] Resolved ", names.length, " compound names");

            string currentName = compound !is null ? compound.name.toLower : "";
            string markup = lbl.label; // Use existing markup
            foreach (name; names)
            {
                if (name.toLower == currentName)
                    continue;

                markup = linkifyCompoundName(markup, name);
            }
            lbl.label = markup;
        }
        catch (Exception e)
            writeln("[ArticleView] Compound resolve failed: ", e.msg);
    }

    /// Walk a container, connect link activation and resolve compound
    /// names on all markup labels.
    void resolveLinksInContainer(Box container)
    {
        if (compound is null)
            return;

        string fullText;

        // Collect plain text from all labels for compound extraction.
        void collectText(Widget w)
        {
            if (w is null)
                return;

            Label lbl = cast(Label) w;
            if (lbl !is null)
            {
                string t = lbl.getText();
                if (t.length > 0)
                    fullText ~= t~" ";
            }
            // Recurse into Box children.
            Box box = cast(Box) w;
            if (box !is null)
            {
                Widget ch = box.getFirstChild();
                while (ch !is null)
                {
                    collectText(ch);
                    ch = ch.getNextSibling();
                }
            }
        }
        collectText(container);

        string[] names = extractCompoundNames(fullText);
        if (names.length == 0)
            return;

        writeln("[ArticleView] Resolved ", names.length, " compound names in container");

        string currentName = compound.name.toLower;

        // Apply links to all markup labels.
        void applyLinks(Widget w)
        {
            if (w is null)
                return;

            Label lbl = cast(Label) w;
            if (lbl !is null && lbl.useMarkup)
            {
                lbl.connectActivateLink(&onLinkActivated);
                string markup = lbl.label;
                foreach (name; names)
                {
                    if (name.toLower == currentName)
                        continue;

                    markup = linkifyCompoundName(markup, name);
                }
                lbl.label = markup;
            }
            Box box = cast(Box) w;
            if (box !is null)
            {
                Widget ch = box.getFirstChild();
                while (ch !is null)
                {
                    applyLinks(ch);
                    ch = ch.getNextSibling();
                }
            }
        }
        applyLinks(container);
    }

    static bool isWordChar(char c)
    {
        return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')
            || (c >= '0' && c <= '9') || c == '-';
    }

    static string linkifyCompoundName(string markup, string name)
    {
        string escaped = name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
        string linked = `<a href="compound:`~name~`">`~escaped~`</a>`;

        // Find first whole-word occurrence not inside a tag
        ptrdiff_t searchFrom = 0;
        while (searchFrom < markup.length)
        {
            ptrdiff_t idx = markup[searchFrom..$].indexOf(escaped);
            if (idx < 0) break;
            idx += searchFrom;

            // Word boundary check: reject partial matches within larger words
            size_t matchEnd = idx + escaped.length;
            bool leftBound = idx == 0 || !isWordChar(markup[idx - 1]);
            bool rightBound = matchEnd >= markup.length || !isWordChar(markup[matchEnd]);

            if (!leftBound || !rightBound)
            {
                searchFrom = idx + 1;
                continue;
            }

            // Check we're not inside an existing <a> tag
            int openTags = 0;
            foreach (i; 0..idx)
            {
                if (markup[i] == '<') openTags++;
                if (markup[i] == '>') openTags--;
            }
            if (openTags <= 0)
            {
                markup = markup[0..idx]~linked~markup[matchEnd..$];
                break;
            }

            searchFrom = idx + 1;
        }
        return markup;
    }

    static string linkifyUrls(string text)
    {
        // Escape Pango markup special chars
        text = text.replace("&", "&amp;");
        text = text.replace("<", "&lt;");
        text = text.replace(">", "&gt;");

        // Convert URLs to <a> tags
        enum urlRe = ctRegex!(`https?://[^\s<>"]+`);
        text = replaceAll!((m) =>
            `<a href="`~m.hit~`">`~m.hit~`</a>`
        )(text, urlRe);

        return text;
    }

    void onViewerClicked()
    {
        if (infobox is null || infobox.compound is null || screenOverlay.getChild() is moleculeView)
            return;

        infobox.subject.remove(moleculeView);
        moleculeView.hexpand = true;
        moleculeView.vexpand = true;
        moleculeView.setBaseZoom(40.0);
        moleculeView.enableMotionControl();

        screenOverlay.setChild(moleculeView);
        screenOverlay.visible = true;
    }
}
