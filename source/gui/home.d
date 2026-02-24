module gui.home;

import std.stdio : writeln;
import std.conv : to;
import std.string : strip;

import gtk.box;
import gtk.label;
import gtk.button;
import gtk.search_entry;
import gtk.list_box;
import gtk.list_box_row;
import gtk.overlay;
import gtk.types : Orientation, Align;

import gui.background : Background;
import gui.loading : makeLoadingDots;
import gui.window : ChemicaWindow;
import akashi.pubchem;

class HomeView : Box
{
private:
    Compound[] compounds;
    SearchEntry searchEntry;
    ListBox suggestionList;
    bool isLoading;

    Box buildResultRow(Compound compound, bool isPrimary = false, bool loading = false)
    {
        Box row = new Box(Orientation.Horizontal, 8);
        row.addCssClass("search-result-row");
        if (!isPrimary)
            row.addCssClass("similar-result");

        if (isPrimary && loading)
        {
            Box dots = makeLoadingDots();
            dots.valign = Align.Center;
            row.append(dots);
        }

        Label title = new Label(compound.name);
        title.addCssClass("search-result-title");
        title.halign = Align.Start;
        title.hexpand = true;
        row.append(title);

        Label cid = new Label(compound.cid.to!string);
        cid.addCssClass("search-result-source");
        cid.halign = Align.End;
        row.append(cid);

        Label src = new Label("PUBCHEM");
        src.addCssClass("search-result-source");
        src.halign = Align.End;
        src.marginStart = 8;
        row.append(src);

        return row;
    }

    void submitSearch()
    {
        if (searchEntry is null)
            return;

        string text = searchEntry.text.strip;
        if (text.length < 2)
            return;

        if (onSearch !is null) onSearch(text);
    }

    void onRowActivated(ListBoxRow row)
    {
        if (row is null || onCompoundSelected is null)
            return;
        int index = row.getIndex();

        void* data = row.getData("compound");
        if (data !is null)
        {
            Compound c = cast(Compound)data;
            if (c !is null)
            {
                onCompoundSelected(index, c);
                return;
            }
        }

        if (index == 0 && compounds.length > 0)
            onCompoundSelected(index, compounds[0]);
    }

public:
    void delegate(string query) onSearch;
    void delegate(int index, Compound compound) onCompoundSelected;

    this()
    {
        super(Orientation.Vertical, 0);

        Overlay overlay = new Overlay();
        overlay.hexpand = true;
        overlay.vexpand = true;

        Background bg = new Background();
        bg.hexpand = true;
        bg.vexpand = true;
        overlay.setChild(bg);

        Box center = new Box(Orientation.Vertical, 0);
        center.hexpand = true;
        center.vexpand = true;
        center.halign = Align.Center;
        center.valign = Align.Center;

        Box content = new Box(Orientation.Vertical, 0);
        content.addCssClass("home-content");
        content.halign = Align.Center;
        content.valign = Align.Start;

        // Logo
        Box logo = new Box(Orientation.Horizontal, 0);
        logo.halign = Align.Center;
        Label logoW = new Label("Wik");
        logoW.addCssClass("home-logo");
        Label logoI = new Label("ia");
        logoI.addCssClass("home-logo");
        logoI.addCssClass("home-logo-accent");
        logo.append(logoW);
        logo.append(logoI);
        content.append(logo);

        Label tagline = new Label("The free chemical compound database");
        tagline.addCssClass("home-tagline");
        tagline.halign = Align.Center;
        content.append(tagline);

        // Search bar
        Box searchBox = new Box(Orientation.Horizontal, 0);
        searchBox.addCssClass("home-search-box");
        searchBox.halign = Align.Center;
        searchBox.widthRequest = 600;

        searchEntry = new SearchEntry();
        searchEntry.placeholderText = "Search for a compound...";
        searchEntry.addCssClass("home-search-entry");
        searchEntry.hexpand = true;
        searchEntry.halign = Align.Fill;
        searchEntry.connectActivate(&submitSearch);
        searchBox.append(searchEntry);

        Button searchBtn = new Button();
        searchBtn.iconName = "system-search-symbolic";
        searchBtn.addCssClass("home-search-button");
        searchBtn.connectClicked(&submitSearch);
        searchBox.append(searchBtn);
        content.append(searchBox);

        // Results list
        suggestionList = new ListBox();
        suggestionList.addCssClass("search-results-container");
        suggestionList.connectRowActivated(&onRowActivated);
        suggestionList.visible = false;
        content.append(suggestionList);

        // Footer links
        Box links = new Box(Orientation.Horizontal, 16);
        links.addCssClass("home-links");
        links.halign = Align.Center;
        links.marginTop = 24;
        links.append(new Label("Powered by"));
        Label pubchemLink = new Label("PUBCHEM");
        pubchemLink.addCssClass("home-link");
        links.append(pubchemLink);

        Button settingsBtn = new Button();
        settingsBtn.iconName = "system-run-symbolic";
        settingsBtn.tooltipText = "Settings";
        settingsBtn.addCssClass("settings-button");
        settingsBtn.connectClicked(() {
            ChemicaWindow.instance.goSettings();
        });
        links.append(settingsBtn);
        content.append(links);

        center.append(content);
        overlay.addOverlay(center);
        append(overlay);
    }

    SearchEntry getSearchEntry() { return searchEntry; }
    ListBox getSuggestionList() { return suggestionList; }

    void addSimilarResults(Compound[] similar)
    {
        if (!isLoading || similar is null || similar.length == 0)
            return;

        foreach (c; similar)
        {
            compounds ~= c;
            ListBoxRow row = new ListBoxRow();
            row.setData("compound", cast(void*)c);
            row.setChild(buildResultRow(c, false));
            suggestionList.append(row);
        }

        isLoading = false;
        // Update primary row to remove loading dots
        if (suggestionList.getFirstChild() !is null && compounds.length > 0)
        {
            ListBoxRow primaryRow = cast(ListBoxRow)suggestionList.getFirstChild();
            if (primaryRow !is null)
                primaryRow.setChild(buildResultRow(compounds[0], true, false));
        }
    }

    void clearResults()
    {
        searchEntry.text = "";
        suggestionList.visible = false;
        suggestionList.removeAll();
        compounds = null;
        isLoading = false;
    }

    void displayError(string msg)
    {
        suggestionList.removeAll();

        ListBoxRow hdr = new ListBoxRow();
        hdr.selectable = false;
        Label hdrLabel = new Label("Error");
        hdrLabel.addCssClass("search-results-header");
        hdrLabel.addCssClass("error-header");
        hdrLabel.halign = Align.Start;
        hdr.setChild(hdrLabel);
        suggestionList.append(hdr);

        ListBoxRow row = new ListBoxRow();
        row.selectable = false;
        Label errLabel = new Label(msg);
        errLabel.addCssClass("search-result-detail");
        errLabel.addCssClass("error-text");
        errLabel.halign = Align.Start;
        row.setChild(errLabel);
        suggestionList.append(row);
        suggestionList.visible = true;
    }

    void displayResults(string query, Compound compound, Compound[] similar = null)
    {
        suggestionList.removeAll();
        compounds = null;
        isLoading = false;

        if (compound is null)
        {
            displayError("No results found for \""~query~"\"");
            return;
        }

        compounds ~= compound;
        bool showLoading = similar is null;
        isLoading = showLoading;

        ListBoxRow primaryRow = new ListBoxRow();
        primaryRow.setChild(buildResultRow(compound, true, showLoading));
        suggestionList.append(primaryRow);

        if (similar !is null && similar.length > 0)
            addSimilarResults(similar);

        suggestionList.visible = true;
    }
}
