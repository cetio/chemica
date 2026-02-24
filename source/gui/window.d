module gui.window;

import std.stdio : writeln;
import std.string : strip;
import core.thread : Thread;
import core.time : dur;

import gtk.application;
import gtk.application_window;
import gtk.header_bar;
import gtk.label;
import gtk.box;
import gtk.overlay;
import gtk.stack;
import gtk.types : Orientation, Align;

import akashi.pubchem;
import akashi.psychonaut : DosageResult, getDosage;

import gui.home;
import gui.article;
import gui.settings : SettingsView;

class ChemicaWindow : ApplicationWindow
{
private:
    Stack stack;
    HomeView home;
    ArticleView article;
    SettingsView settings;

    Compound lastSearchCompound;
    Overlay windowOverlay;
    Label titleLabel;

    static ChemicaWindow _instance;

public:
    static ChemicaWindow instance()
    {
        return _instance;
    }

    this(Application app)
    {
        super(app);
        _instance = this;

        setDefaultSize(1200, 800);
        setTitle("Chemica");

        HeaderBar header = new HeaderBar();
        header.showTitleButtons = true;
        titleLabel = new Label("Chemica");
        header.titleWidget = titleLabel;
        setTitlebar(header);

        windowOverlay = new Overlay();
        windowOverlay.hexpand = true;
        windowOverlay.vexpand = true;

        stack = new Stack();
        stack.hexpand = true;
        stack.vexpand = true;

        home = new HomeView();
        home.onSearch = &doSearch;
        home.onCompoundSelected = &onCompoundSelected;
        stack.addNamed(home, "home");

        article = new ArticleView();
        article.onCompoundNavigate = &onCompoundNavigate;
        stack.addNamed(article, "article");

        settings = new SettingsView();
        stack.addNamed(settings, "settings");

        stack.visibleChildName = "home";

        Box root = new Box(Orientation.Vertical, 0);
        root.addCssClass("root-container");
        root.hexpand = true;
        root.vexpand = true;
        root.append(stack);
        windowOverlay.setChild(root);

        setChild(windowOverlay);
    }

    void goHome()
    {
        titleLabel.label = "Chemica";
        stack.visibleChildName = "home";
        lastSearchCompound = null;
        article.clearArticle();
        home.clearResults();
    }

    void goSettings()
    {
        titleLabel.label = "Settings";
        stack.visibleChildName = "settings";
    }

    void goArticle(string title)
    {
        onCompoundNavigate(title);
    }

    void goArticle(Compound compound)
    {
        if (compound is null)
            return;
        lastSearchCompound = compound;
        article.fromCompound(compound);
        stack.visibleChildName = "article";

        Thread dosageThread = new Thread({
            try
            {
                DosageResult dosage = getDosage(compound);
                article.infobox.setDosage(dosage);
            }
            catch (Exception e)
                writeln("[ChemicaWindow] Dosage fetch failed: ", e.msg);
        });
        dosageThread.start();
    }

private:
    void doSearch(string query)
    {
        string q = query.strip;
        if (q.length < 2)
            return;

        lastSearchCompound = getProperties(q);

        if (lastSearchCompound is null)
        {
            home.displayResults(q, lastSearchCompound);
            return;
        }

        home.displayResults(q, lastSearchCompound, null);

        Thread similarThread = new Thread({
            try
            {
                Compound[] similar = similaritySearch(lastSearchCompound.cid, 85, 10);

                Compound[] filtered;
                foreach (compound; similar)
                {
                    if (compound.cid != lastSearchCompound.cid)
                        filtered ~= compound;
                }

                if (filtered.length > 4)
                    filtered = filtered[0..4];

                Thread.sleep(100.dur!"msecs");
                home.addSimilarResults(filtered);
            }
            catch (Exception e)
                writeln("[ChemicaWindow] Similarity search failed: ", e.msg);
        });
        similarThread.start();
    }

    void onCompoundSelected(int index, Compound compound)
    {
        if (compound is null)
            return;
        goArticle(compound);
    }

    void onCompoundNavigate(string compoundName)
    {
        Thread navThread = new Thread({
            try
            {
                Compound compound = getProperties(compoundName);
                if (compound is null)
                    return;
                lastSearchCompound = compound;
                article.fromCompound(compound);

                DosageResult dosage = getDosage(compound);
                article.infobox.setDosage(dosage);
            }
            catch (Exception e)
                writeln("[ChemicaWindow] Compound navigate failed: ", e.msg);
        });
        navThread.start();
    }
}
