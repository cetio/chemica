module gui.settings;

import std.stdio : writeln;
import std.conv : to;
import std.algorithm : canFind;

import gtk.box;
import gtk.image;
import gtk.label;
import gtk.button;
import gtk.check_button;
import gtk.entry;
import gtk.stack;
import gtk.types : Orientation, Align, InputPurpose;

import infer.config;
import gui.window : ChemicaWindow;

class SettingsView : Box
{
private:
    Entry endpointEntry;
    Entry apiKeyEntry;
    Entry chatModelEntry;
    Entry embedModelEntry;
    Entry groupThreshEntry;
    Entry dedupeThreshEntry;
    CheckButton rabbitHolesCheck;
    CheckButton srcWikipediaCheck;
    CheckButton srcPsychonautCheck;

    Button[] tabButtons;
    Stack contentStack;

    Box buildEntryRow(string labelText, Entry field, string placeholder = "")
    {
        Box row = new Box(Orientation.Vertical, 2);
        row.addCssClass("settings-row");
        row.hexpand = true;
        row.halign = Align.Fill;

        Label lbl = new Label(labelText);
        lbl.addCssClass("settings-label");
        lbl.halign = Align.Start;
        row.append(lbl);

        field.addCssClass("settings-entry");
        field.hexpand = true;
        field.halign = Align.Fill;
        if (placeholder.length > 0)
            field.placeholderText = placeholder;
        row.append(field);

        return row;
    }

    static Label buildSectionTitle(string text)
    {
        Label title = new Label(text);
        title.addCssClass("settings-section-title");
        title.halign = Align.Start;
        title.marginTop = 12;
        title.marginBottom = 4;
        return title;
    }

    void selectTab(int index)
    {
        foreach (i, btn; tabButtons)
        {
            if (i == index)
                btn.addCssClass("settings-tab-active");
            else
                btn.removeCssClass("settings-tab-active");
        }

        final switch (index)
        {
            case 0: contentStack.visibleChildName = "inference"; break;
            case 1: contentStack.visibleChildName = "retrieval"; break;
            case 2: contentStack.visibleChildName = "style"; break;
        }
    }

    Box buildInferenceTab()
    {
        Box tab = new Box(Orientation.Vertical, 4);
        tab.addCssClass("settings-section");

        tab.append(buildSectionTitle("Local AI"));

        endpointEntry = new Entry();
        endpointEntry.text = config.endpoint;
        tab.append(buildEntryRow("Endpoint", endpointEntry, "http://127.0.0.1:1234/"));

        apiKeyEntry = new Entry();
        if (config.apiKey.length > 0)
            apiKeyEntry.text = config.apiKey;
        apiKeyEntry.inputPurpose = InputPurpose.Password;
        apiKeyEntry.visibility = false;
        tab.append(buildEntryRow("API Key", apiKeyEntry, "sk-... (optional for local)"));

        chatModelEntry = new Entry();
        chatModelEntry.text = config.chatModel;
        tab.append(buildEntryRow("Chat Model", chatModelEntry, "model name or path"));

        embedModelEntry = new Entry();
        embedModelEntry.text = config.embedModel;
        tab.append(buildEntryRow("Embed Model", embedModelEntry, "embedding model name"));

        groupThreshEntry = new Entry();
        groupThreshEntry.text = config.groupingThreshold.to!string;
        tab.append(buildEntryRow("Group Threshold", groupThreshEntry, "0.75"));

        dedupeThreshEntry = new Entry();
        dedupeThreshEntry.text = config.dedupeThreshold.to!string;
        tab.append(buildEntryRow("Dedup Threshold", dedupeThreshEntry, "0.92"));

        tab.append(buildSectionTitle("Interface"));

        rabbitHolesCheck = new CheckButton();
        rabbitHolesCheck.label = "Auto resolve rabbit-holes";
        rabbitHolesCheck.active = config.autoResolveRabbitHoles;
        rabbitHolesCheck.marginTop = 4;
        tab.append(rabbitHolesCheck);

        return tab;
    }

    Box buildSourceRow(string iconPath, string sourceName, ref CheckButton check, bool active)
    {
        Box row = new Box(Orientation.Horizontal, 8);
        row.addCssClass("settings-source-row");
        row.halign = Align.Fill;
        row.hexpand = true;
        row.marginStart = 4;
        row.marginTop = 2;
        row.marginBottom = 2;

        Image icon = Image.newFromFile(iconPath);
        icon.pixelSize = 16;
        row.append(icon);

        check = new CheckButton();
        check.label = sourceName;
        check.active = active;
        check.addCssClass("settings-source-check");
        row.append(check);

        return row;
    }

    Box buildRetrievalTab()
    {
        Box tab = new Box(Orientation.Vertical, 4);
        tab.addCssClass("settings-section");

        tab.append(buildSectionTitle("Sources"));

        tab.append(buildSourceRow(
            "resources/icons/wikipedia.svg", "Wikipedia",
            srcWikipediaCheck, config.enabledSources.canFind("wikipedia")));

        tab.append(buildSourceRow(
            "resources/icons/psychonaut.svg", "Psychonaut Wiki",
            srcPsychonautCheck, config.enabledSources.canFind("psychonaut")));

        return tab;
    }

    static Box buildPlaceholderTab(string text)
    {
        Box tab = new Box(Orientation.Vertical, 0);
        tab.addCssClass("settings-section");
        tab.halign = Align.Center;
        tab.valign = Align.Center;
        tab.vexpand = true;

        Label placeholder = new Label(text);
        placeholder.addCssClass("settings-placeholder");
        tab.append(placeholder);
        return tab;
    }

public:
    this()
    {
        super(Orientation.Vertical, 0);
        hexpand = true;
        vexpand = true;

        // Nav bar with back button
        Box nav = new Box(Orientation.Horizontal, 0);
        nav.addCssClass("article-nav");
        nav.hexpand = true;
        nav.halign = Align.Fill;

        Button backBtn = new Button();
        backBtn.iconName = "go-previous-symbolic";
        backBtn.tooltipText = "Back to home";
        backBtn.addCssClass("nav-home-button");
        backBtn.addCssClass("nav-back-button");
        backBtn.connectClicked(() {
            ChemicaWindow.instance.goHome();
        });
        backBtn.halign = Align.Start;
        backBtn.valign = Align.Center;
        nav.append(backBtn);

        Label navTitle = new Label("Settings");
        navTitle.addCssClass("article-nav-title");
        navTitle.halign = Align.Start;
        navTitle.hexpand = true;
        navTitle.xalign = 0;
        navTitle.marginStart = 8;
        nav.append(navTitle);
        append(nav);

        // Tab bar
        Box tabBar = new Box(Orientation.Horizontal, 0);
        tabBar.addCssClass("settings-tab-bar");
        tabBar.halign = Align.Fill;
        tabBar.hexpand = true;

        string[3] tabNames = ["Inference", "Retrieval", "Style"];
        foreach (i, name; tabNames)
        {
            Button tab = new Button();
            tab.label = name;
            tab.addCssClass("settings-tab");
            tab.connectClicked(((int idx) => () { selectTab(idx); })(cast(int)i));
            tabBar.append(tab);
            tabButtons ~= tab;
        }
        append(tabBar);

        // Content stack
        contentStack = new Stack();
        contentStack.hexpand = true;
        contentStack.vexpand = true;

        contentStack.addNamed(buildInferenceTab(), "inference");
        contentStack.addNamed(buildRetrievalTab(), "retrieval");
        contentStack.addNamed(buildPlaceholderTab("Style settings coming soon."), "style");
        contentStack.visibleChildName = "inference";
        append(contentStack);

        // Apply button
        Box footer = new Box(Orientation.Horizontal, 0);
        footer.halign = Align.End;
        footer.marginTop = 8;
        footer.marginEnd = 16;
        footer.marginBottom = 12;

        Button applyBtn = new Button();
        applyBtn.label = "Apply";
        applyBtn.addCssClass("settings-apply");
        applyBtn.connectClicked(&onApply);
        footer.append(applyBtn);
        append(footer);

        selectTab(0);
    }

    void onApply()
    {
        InferConfig cfg;
        cfg.endpoint = endpointEntry.text;
        cfg.apiKey = apiKeyEntry.text;
        cfg.chatModel = chatModelEntry.text;
        cfg.embedModel = embedModelEntry.text;
        cfg.autoResolveRabbitHoles = rabbitHolesCheck.active;

        try
            cfg.groupingThreshold = groupThreshEntry.text.to!float;
        catch (Exception e)
            cfg.groupingThreshold = 0.75;

        try
            cfg.dedupeThreshold = dedupeThreshEntry.text.to!float;
        catch (Exception e)
            cfg.dedupeThreshold = 0.92;

        string[] sources;
        if (srcWikipediaCheck.active) sources ~= "wikipedia";
        if (srcPsychonautCheck.active) sources ~= "psychonaut";
        cfg.enabledSources = sources;

        config = cfg;
        writeln("[Settings] Config updated: endpoint=", cfg.endpoint,
            " chat=", cfg.chatModel, " embed=", cfg.embedModel,
            " rabbitHoles=", cfg.autoResolveRabbitHoles,
            " sources=", cfg.enabledSources);
    }
}
