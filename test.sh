curl -X POST http://localhost:5000/post-message \
-H "Content-Type: application/json" \
-d '{"author":"fermion", "message": "Hello from admin!"}'

curl http://localhost:5000/history/fermion
