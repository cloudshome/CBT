using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Sky.Companion;

/// <summary>
/// HTTPS client for the Ubuntu Hub. Pairing, loop-health and paper mutations
/// only. There is no order, withdraw, or signed-exchange method on this type.
/// </summary>
public sealed class HubClient
{
    private readonly HttpClient _http;
    private readonly string _origin;
    private readonly string _token;

    public HubClient(string origin, string token, HttpClient? http = null)
    {
        _origin = ValidateOrigin(origin);
        _token = token ?? throw new ArgumentNullException(nameof(token));
        _http = http ?? new HttpClient();
    }

    public static string ValidateOrigin(string url)
    {
        if (string.IsNullOrWhiteSpace(url))
            throw new ArgumentException("hub URL is required");
        var raw = url.Trim().TrimEnd('/');
        if (!raw.Contains("://", StringComparison.Ordinal))
            raw = "https://" + raw;
        if (!Uri.TryCreate(raw, UriKind.Absolute, out var uri))
            throw new ArgumentException("hub URL is not a valid URI");
        var host = uri.Host.ToLowerInvariant();
        var loopback = host is "127.0.0.1" or "localhost" or "::1" || host.StartsWith("127.");
        if (uri.Scheme == "http" && !loopback)
            throw new ArgumentException("remote companions require HTTPS");
        if (uri.Scheme is not ("https" or "http"))
            throw new ArgumentException("unsupported URL scheme");
        return $"{uri.Scheme}://{uri.Authority}";
    }

    public HttpRequestMessage Read(string path)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, _origin + path);
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
        req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        req.Headers.TryAddWithoutValidation("X-SKY-Client-Version", AppConfig.ClientBuild.ToString());
        return req;
    }

    public HttpRequestMessage Mutate(string path, string jsonBody, string idempotencyKey)
    {
        if (string.IsNullOrWhiteSpace(idempotencyKey) || idempotencyKey.Length < 8)
            throw new ArgumentException("idempotency key too short");
        var req = new HttpRequestMessage(HttpMethod.Post, _origin + path)
        {
            Content = new StringContent(jsonBody, Encoding.UTF8, "application/json"),
        };
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
        req.Headers.TryAddWithoutValidation("X-SKY-Client-Version", AppConfig.ClientBuild.ToString());
        req.Headers.TryAddWithoutValidation("Idempotency-Key", idempotencyKey);
        return req;
    }

    public static string PairingBody(string code, string deviceName)
    {
        return JsonSerializer.Serialize(new
        {
            code,
            name = deviceName,
            client = AppConfig.ClientName,
            client_build = AppConfig.ClientBuild,
            live_exchange_execution = AppConfig.LiveExchangeExecution,
        });
    }
}
