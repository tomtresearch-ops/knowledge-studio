#!/bin/bash

# YouTube Intelligence - Always Running Launcher
# Double-click this to start the server and keep it running

cd "$(dirname "$0")"

echo "🚀 YouTube Intelligence - Always Running Mode"
echo "This will start the server and keep it running in the background"
echo "You can close this window and the server will keep running!"
echo ""

# Start the persistent service
./start_persistent.sh

echo ""
echo "✅ Server is now running in the background!"
echo "📱 Access it at: http://localhost:5001"
echo "📚 Library: http://localhost:5001/library"
echo ""
echo "To stop the server later, run: ./stop_server.sh"
echo "Or double-click STOP_SERVER.command"
echo ""
echo "Press any key to close this window (server will keep running)..."
read -n 1


