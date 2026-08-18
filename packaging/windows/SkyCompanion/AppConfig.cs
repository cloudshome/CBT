namespace Sky.Companion;

/// <summary>
/// Compile-time companion identity. The Hub remains the only database,
/// risk gate and paper runner. This process never places an exchange order.
/// </summary>
public static class AppConfig
{
    public const string ClientName = "sky-windows";
    public const int ClientBuild = 1;
    public const string Version = "2.40.0";
    public const bool LiveExchangeExecution = false;
    public const string ApiPrefix = "/api/v1";
    public const string CredentialTarget = "SKY/HubDeviceToken";

    public static readonly string[] AllowedSchemes = { "https" };
}
