//! Exercises the public server-side extension negotiation API exactly as an
//! external server performing its own HTTP upgrade would: negotiate the
//! client's `Sec-WebSocket-Extensions` offer, construct a `WebSocket` via
//! `from_raw_socket_with_extensions`, and round-trip a compressed message.

#![cfg(all(feature = "handshake", feature = "deflate"))]

use std::{
    net::{TcpListener, TcpStream},
    thread::spawn,
};

use tungstenite::{
    extensions::ExtensionsConfig,
    protocol::{Role, WebSocket, WebSocketConfig},
    Error, Message,
};

#[test]
fn negotiate_offers_then_round_trip_compressed_message() {
    // The client's Sec-WebSocket-Extensions request header value, as a manual
    // HTTP upgrade would surface it.
    let client_offer = "permessage-deflate; client_max_window_bits";

    let mut server_extensions_config = ExtensionsConfig::default();
    server_extensions_config.permessage_deflate = Some(Default::default());

    let (extensions, response_header) = server_extensions_config
        .negotiate_offers([client_offer])
        .expect("negotiation should succeed");
    let response_header = response_header.expect("offer should be accepted");
    assert!(response_header.starts_with("permessage-deflate"));

    let listener = TcpListener::bind("127.0.0.1:0").expect("can't listen");
    let addr = listener.local_addr().unwrap();

    let server = spawn(move || {
        let (stream, _) = listener.accept().unwrap();
        let mut websocket =
            WebSocket::from_raw_socket_with_extensions(stream, Role::Server, None, extensions);

        let message = websocket.read().unwrap();
        websocket.send(message).unwrap();

        let message = websocket.read().unwrap(); // client's close
        assert!(message.is_close());
        match websocket.read().unwrap_err() {
            Error::ConnectionClosed => {}
            err => panic!("unexpected error: {err:?}"),
        }
    });

    // The "client" endpoint enables permessage-deflate with the same default
    // parameters that the server's response header agreed to.
    let mut client_config = WebSocketConfig::default();
    client_config.extensions.permessage_deflate = Some(Default::default());

    let stream = TcpStream::connect(addr).unwrap();
    let mut websocket = WebSocket::from_raw_socket(stream, Role::Client, Some(client_config));

    let payload = "the quick brown fox jumps over the lazy dog ".repeat(2048);
    websocket.send(Message::text(payload.clone())).unwrap();

    let echoed = websocket.read().unwrap();
    assert_eq!(echoed.into_text().unwrap().as_str(), payload);

    websocket.close(None).unwrap();
    let message = websocket.read().unwrap(); // server's close acknowledgement
    assert!(message.is_close());
    match websocket.read().unwrap_err() {
        Error::ConnectionClosed => {}
        err => panic!("unexpected error: {err:?}"),
    }

    server.join().unwrap();
}
