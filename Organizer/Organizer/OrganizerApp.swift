//
//  OrganizerApp.swift
//  Organizer
//
//  Created by Carlos Aguilar
//

import SwiftUI

@main
struct OrganizerApp: App {
    var body: some Scene {
        MenuBarExtra {
            ContentView()
                .frame(width: 480, height: 680)
        } label: {
            Image(systemName: "folder.badge.gearshape")
        }
        .menuBarExtraStyle(.window)
    }
}
