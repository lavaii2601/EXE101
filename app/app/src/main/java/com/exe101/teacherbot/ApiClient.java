package com.exe101.teacherbot;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class ApiClient {
    private static final int MAX_RESPONSE_CHARS = 2_000_000;
    private String baseUrl;
    private String accessToken = "";

    public ApiClient(String baseUrl) {
        setBaseUrl(baseUrl);
    }

    public void setBaseUrl(String value) {
        String next = value == null || value.trim().isEmpty()
                ? "http://10.0.2.2:5000/api"
                : value.trim();
        while (next.endsWith("/")) {
            next = next.substring(0, next.length() - 1);
        }
        if (!next.endsWith("/api")) {
            next = next + "/api";
        }
        validateBaseUrl(next);
        baseUrl = next;
    }

    private void validateBaseUrl(String value) {
        try {
            URL parsed = new URL(value);
            String scheme = parsed.getProtocol();
            String host = parsed.getHost();
            if ("https".equalsIgnoreCase(scheme)) return;
            if (BuildConfig.DEBUG && "http".equalsIgnoreCase(scheme) && isPrivateDevelopmentHost(host)) return;
            throw new IllegalArgumentException("Backend URL must use HTTPS");
        } catch (IOException error) {
            throw new IllegalArgumentException("Invalid backend URL", error);
        }
    }

    private boolean isPrivateDevelopmentHost(String host) {
        if (host == null) return false;
        if ("localhost".equalsIgnoreCase(host) || "10.0.2.2".equals(host) || host.startsWith("127.")) return true;
        if (host.startsWith("10.") || host.startsWith("192.168.")) return true;
        if (host.startsWith("172.")) {
            String[] parts = host.split("\\.");
            if (parts.length > 1) {
                try {
                    int second = Integer.parseInt(parts[1]);
                    return second >= 16 && second <= 31;
                } catch (NumberFormatException ignored) {
                    return false;
                }
            }
        }
        return false;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setUserId(String value) {
        // Kept for source compatibility. User identity is no longer trusted as a header.
    }

    public void setAccessToken(String value) {
        accessToken = value == null ? "" : value.trim();
    }

    public JSONObject get(String path) throws Exception {
        return request("GET", path, null);
    }

    public JSONObject post(String path, JSONObject body) throws Exception {
        return request("POST", path, body);
    }

    public JSONObject patch(String path, JSONObject body) throws Exception {
        return request("PATCH", path, body);
    }

    public JSONObject delete(String path) throws Exception {
        return request("DELETE", path, null);
    }

    private JSONObject request(String method, String path, JSONObject body) throws Exception {
        URL url = new URL(baseUrl + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod(method);
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(30000);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        if (!accessToken.isEmpty()) {
            connection.setRequestProperty("Authorization", "Bearer " + accessToken);
        }

        if (body != null) {
            connection.setDoOutput(true);
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream stream = connection.getOutputStream()) {
                stream.write(bytes);
            }
        }

        int status = connection.getResponseCode();
        String text = readAll(status >= 400 ? connection.getErrorStream() : connection.getInputStream());
        connection.disconnect();

        JSONObject data = text.isEmpty() ? new JSONObject() : new JSONObject(text);
        if (status >= 400) {
            String message = data.optString("error", data.optString("message", "HTTP " + status));
            throw new IOException(message);
        }
        return data;
    }

    private String readAll(InputStream stream) throws IOException {
        if (stream == null) return "";
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
                if (builder.length() > MAX_RESPONSE_CHARS) {
                    throw new IOException("Server response is too large");
                }
            }
        }
        return builder.toString();
    }
}
