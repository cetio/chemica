module gui.article.reports;

import std.stdio : writeln;
import core.thread : Thread;

import gtk.box;
import gtk.label;
import gtk.gesture_click;
import gtk.types : Orientation, Align;

import gui.article.expander;
import akashi.page : Page;
import akashi.psychonaut : getReports, getPagesByTitle;

class Reports : Expander
{
private:
    string compoundName;
    Page[] fetchedReports;

public:
    void delegate(Page report) onReportSelected;

    this(string compName)
    {
        super("Reports");
        compoundName = compName;
        onFirstExpand = &doFetch;
    }

    void doFetch()
    {
        Thread t = new Thread({
            Label loadingLabel = new Label("Loading reports...");
            loadingLabel.addCssClass("expander-detail");
            loadingLabel.halign = Align.Start;
            addContent(loadingLabel);

            try
            {
                Page[] pages = getPagesByTitle!"psychonaut"(compoundName);
                Page[] reports;
                if (pages.length > 0)
                    reports = getReports(pages[0]);

                content.remove(loadingLabel);
                populate(reports);
            }
            catch (Exception e)
            {
                writeln("[Reports] Fetch failed: ", e.msg);
                content.remove(loadingLabel);
                populate(null);
            }
        });
        t.start();
    }

    void populate(Page[] reports)
    {
        if (reports is null || reports.length == 0)
        {
            Label noResults = new Label("No reports found.");
            noResults.addCssClass("expander-detail");
            noResults.halign = Align.Start;
            addContent(noResults);
            return;
        }

        fetchedReports = reports;

        foreach (report; reports)
        {
            Box reportRow = new Box(Orientation.Horizontal, 0);
            reportRow.addCssClass("search-result-row");
            reportRow.hexpand = true;

            Label titleLabel = new Label(report.title);
            titleLabel.addCssClass("search-result-title");
            titleLabel.tooltipText = report.url;
            titleLabel.halign = Align.Start;
            titleLabel.xalign = 0;
            titleLabel.hexpand = true;
            titleLabel.wrap = true;
            reportRow.append(titleLabel);

            GestureClick rowClick = new GestureClick();
            rowClick.connectReleased(((r) => (int n, double x, double y) {
                if (onReportSelected !is null)
                    onReportSelected(r);
            })(report));
            reportRow.addController(rowClick);

            addContent(reportRow);
        }
    }
}