// Runs inside KWin; only window metadata is sent to Morok's local session bus.
const service = "org.morok.Assistant";
const path = "/DesktopIntegration";
const iface = "org.morok.DesktopIntegration";

function isMorokApp(window) {
    const desktop = String(window.desktopFileName || "").toLowerCase();
    const klass = String(window.resourceClass || "").toLowerCase();
    return desktop === "morok-assistant" || desktop.endsWith("/morok-assistant.desktop")
        || klass === "morok-assistant" || klass === "morok assistant"
        || String(window.resourceName || "").toLowerCase() === "morok-assistant";
}

function publish(window) {
    if (!window || window.deleted || window.desktopWindow || window.dock) {
        return;
    }
    if (window.minimized) {
        callDBus(service, path, iface, "forget_window", String(window.internalId));
        return;
    }
    if (isMorokApp(window) || String(window.caption || "") === "Морок") {
        if (String(window.caption || "") === "Морок") {
            window.skipTaskbar = true;
            window.skipPager = true;
            window.skipSwitcher = true;
            window.keepAbove = true;
            window.onAllDesktops = true;
            window.noBorder = true;
        }
        return;
    }
    callDBus(service, path, iface, "update_window", String(window.internalId),
        String(window.caption || ""), String(window.resourceClass || ""),
        Math.round(window.x), Math.round(window.y),
        Math.round(window.width), Math.round(window.height),
        Boolean(window.fullScreen), Boolean(window.keepAbove));
}

function publishActive() {
    const active = workspace.activeWindow;
    callDBus(service, path, iface, "set_active_window",
        active && !isMorokApp(active) && String(active.caption || "") !== "Морок"
            ? String(active.internalId) : "morok");
}

function watch(window) {
    publish(window);
    window.frameGeometryChanged.connect(function () { publish(window); });
    window.captionChanged.connect(function () { publish(window); });
    window.fullScreenChanged.connect(function () { publish(window); });
    window.keepAboveChanged.connect(function () { publish(window); });
    window.minimizedChanged.connect(function () { publish(window); });
    window.desktopFileNameChanged.connect(function () { publish(window); });
}

workspace.windowAdded.connect(function (window) {
    watch(window);
    publishActive();
});
workspace.windowRemoved.connect(function (window) {
    callDBus(service, path, iface, "forget_window", String(window.internalId));
    publishActive();
});
workspace.windowActivated.connect(function (window) {
    publish(window);
    publishActive();
});
for (const window of workspace.stackingOrder) {
    watch(window);
}
publishActive();
