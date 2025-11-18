package com.mycompany.app;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.util.Optional;

/**
 * Simple HTTP server that responds with Hello World.
 */
public class App {

    private static final String MESSAGE = "Hello World ductt!";
    private static final String ENV_PORT = "PORT";
    private static final int DEFAULT_PORT = 8080;

    public App() {}

    public static void main(String[] args) throws IOException {
        int port = Optional.ofNullable(System.getenv(ENV_PORT))
                .map(Integer::parseInt)
                .orElse(DEFAULT_PORT);

        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/", new HelloHandler());
        server.setExecutor(null); // default executor
        System.out.println("Server started on port " + port);
        server.start();
    }

    public String getMessage() {
        return MESSAGE;
    }

    private static class HelloHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            byte[] response = MESSAGE.getBytes();
            exchange.sendResponseHeaders(200, response.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(response);
            }
        }
    }
}
