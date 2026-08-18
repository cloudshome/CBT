namespace Sky.Companion;

/// <summary>
/// WinForms + WebView2 shell. First run pairs with the Hub; afterwards the
/// workstation is loaded over HTTPS. Offline = read-only banner. No local
/// paper runner and no exchange-order path.
/// </summary>
internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new CompanionForm());
    }
}

internal sealed class CompanionForm : Form
{
    public CompanionForm()
    {
        Text = $"SKY companion {AppConfig.Version}";
        Width = 1280;
        Height = 800;
        var banner = new Label
        {
            Dock = DockStyle.Top,
            Height = 28,
            Text = "Hub client only — live_exchange_execution=false — mutations require HTTPS + token + Idempotency-Key",
        };
        Controls.Add(banner);
    }
}
