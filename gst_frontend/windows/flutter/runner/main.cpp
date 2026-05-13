// This file configures a Flutter Driven Application.
// https://flutter.dev/docs/development/platform-integration/c-interop

#include "flutter/generated_plugin_registrant.h"

#include <generated_plugin_registrant.h>

int main(int argc, char** argv) {
    // Initialize Flutter engine
    flutter::FlutterWindowController controller;
    // Register plugins
    RegisterPlugins(controller.registrar());
    controller.Run();
    return 0;
}