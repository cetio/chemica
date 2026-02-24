module app;

import std.file : exists, readText;
import std.stdio : writeln;

import gio.types : ApplicationFlags;
import gtk.application;
import gtk.css_provider;
import gtk.style_context;
import gdk.display;
import gtk.types : STYLE_PROVIDER_PRIORITY_APPLICATION;

import gui.window : ChemicaWindow;

immutable string cssPath = "resources/style.css";

class ChemicaApp : Application
{
private:
    CssProvider cssProvider;

    void applyCss()
    {
        cssProvider = new CssProvider();
        if (cssPath.exists)
            cssProvider.loadFromString(cssPath.readText);
        else
            writeln("Warning: CSS file not found at "~cssPath);

        StyleContext.addProviderForDisplay(
            Display.getDefault(), cssProvider, STYLE_PROVIDER_PRIORITY_APPLICATION);
    }

    void onActivate()
    {
        applyCss();
        ChemicaWindow window = new ChemicaWindow(this);
        window.present();
    }

public:
    this()
    {
        super("org.chemica.pubchem", ApplicationFlags.DefaultFlags);
        connectActivate(&onActivate);
    }
}

void main(string[] args)
{
    ChemicaApp app = new ChemicaApp();
    app.run(args);
}
