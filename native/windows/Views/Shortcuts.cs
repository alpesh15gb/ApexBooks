using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.System;
using static ApexBooks_Windows.Views.NativeUi;

namespace ApexBooks_Windows;

public sealed partial class MainPage
{
    // Keyboard-first billing, matching the web app: Alt+<key>; ignored while a dialog or editor is open. F1 lists them.
    private static readonly (VirtualKey Key, bool Create, string Target, string Label)[] Shortcuts =
    [
        (VirtualKey.N, true, "sales_invoice", "New sales invoice"), (VirtualKey.E, true, "estimate", "New estimate"),
        (VirtualKey.R, true, "payment_in", "Record payment received"), (VirtualKey.P, true, "purchase_bill", "New purchase bill"),
        (VirtualKey.X, true, "expense", "New expense"), (VirtualKey.S, false, "pos", "Open POS"),
        (VirtualKey.H, false, "dashboard", "Dashboard"), (VirtualKey.I, false, "sales_invoice", "Sales invoices"),
        (VirtualKey.C, false, "party", "Parties"), (VirtualKey.T, false, "item", "Items"),
        (VirtualKey.D, false, "day_book", "Day book"), (VirtualKey.G, false, "reports", "Reports"),
    ];

    private void InstallShortcuts(UIElement target)
    {
        foreach (var shortcut in Shortcuts)
        {
            var accelerator = new KeyboardAccelerator { Key = shortcut.Key, Modifiers = VirtualKeyModifiers.Menu };
            accelerator.Invoked += async (_, args) =>
            {
                args.Handled = true;
                if (DialogOpen || CompanyId.Length == 0 || !recordsReady) return;
                if (shortcut.Create && !CanWrite) return;
                await Run(() => shortcut.Create ? NewEntry(shortcut.Target) : Navigate(shortcut.Target));
            };
            target.KeyboardAccelerators.Add(accelerator);
        }
        var help = new KeyboardAccelerator { Key = VirtualKey.F1 };
        help.Invoked += async (_, args) => { args.Handled = true; if (!DialogOpen) await Run(ShortcutHelp); };
        target.KeyboardAccelerators.Add(help);
        target.KeyboardAcceleratorPlacementMode = KeyboardAcceleratorPlacementMode.Hidden;
    }

    private async Task ShortcutHelp()
    {
        var grid = new Grid { ColumnSpacing = 18, RowSpacing = 8 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var rows = Shortcuts.Select(s => ("Alt + " + s.Key, s.Label)).Concat([("Ctrl + Enter", "Save the open document"), ("Esc", "Close the dialog"), ("F1", "Show this list")]).ToList();
        for (var i = 0; i < rows.Count; i++)
        {
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var keys = Text(rows[i].Item1, 13, true); var label = Text(rows[i].Item2, 13);
            Grid.SetRow(keys, i); Grid.SetRow(label, i); Grid.SetColumn(label, 1); grid.Children.Add(keys); grid.Children.Add(label);
        }
        await Dialog("Keyboard shortcuts", grid, () => Task.CompletedTask, "Done");
    }
}
