package com.humanfall.falldetect.net;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Minimal HTTP/1.1 server for unit tests, built on java.net.ServerSocket only (unit tests compile
 * against the Android API, which has no com.sun.net.httpserver). One request per connection.
 */
final class FakeHttpServer implements AutoCloseable {
    interface Handler {
        /** Returns {status code, JSON body}. headers keys are lower case. */
        Object[] handle(String method, String path, Map<String, String> headers, String body) throws Exception;
    }

    private final ServerSocket socket;
    private final Thread thread;

    FakeHttpServer(Handler handler) throws IOException {
        socket = new ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"));
        thread = new Thread(() -> {
            while (!socket.isClosed()) {
                try (Socket client = socket.accept()) {
                    serve(client, handler);
                } catch (IOException e) {
                    // 서버를 닫을 때 accept 가 끝나며 생기는 예외
                }
            }
        }, "fake-http");
        thread.setDaemon(true);
        thread.start();
    }

    int port() {
        return socket.getLocalPort();
    }

    @Override
    public void close() throws IOException {
        socket.close();
    }

    private static void serve(Socket client, Handler handler) throws IOException {
        InputStream in = client.getInputStream();
        String[] requestLine = readLine(in).split(" ");
        Map<String, String> headers = new HashMap<>();
        for (String line = readLine(in); !line.isEmpty(); line = readLine(in)) {
            int colon = line.indexOf(':');
            if (colon > 0) {
                headers.put(line.substring(0, colon).trim().toLowerCase(Locale.ROOT), line.substring(colon + 1).trim());
            }
        }
        int length = Integer.parseInt(headers.getOrDefault("content-length", "0"));
        byte[] body = new byte[length];
        int read = 0;
        while (read < length) {
            int n = in.read(body, read, length - read);
            if (n < 0) {
                break;
            }
            read += n;
        }
        Object[] reply;
        try {
            reply = handler.handle(requestLine[0], requestLine[1], headers, new String(body, 0, read, StandardCharsets.UTF_8));
        } catch (Exception e) {
            // 테스트 처리기 오류는 서버 오류(500)로 돌려줌
            reply = new Object[]{500, "{\"detail\":\"" + e.getClass().getSimpleName() + "\"}"};
        }
        byte[] out = ((String) reply[1]).getBytes(StandardCharsets.UTF_8);
        OutputStream os = client.getOutputStream();
        os.write(("HTTP/1.1 " + reply[0] + " X\r\nContent-Type: application/json; charset=utf-8\r\n"
                + "Content-Length: " + out.length + "\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
        os.write(out);
        os.flush();
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        int c;
        while ((c = in.read()) != -1 && c != '\n') {
            if (c != '\r') {
                line.write(c);
            }
        }
        return line.toString("UTF-8");
    }
}
