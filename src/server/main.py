from src.server.grpc_service import create_server


def main() -> None:
    server = create_server()
    server.start()
    print("Poker gRPC server listening on localhost:50051")
    server.wait_for_termination()


if __name__ == "__main__":
    main()
