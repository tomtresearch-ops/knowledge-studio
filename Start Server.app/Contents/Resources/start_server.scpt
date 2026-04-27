on run
    set scriptPath to POSIX path of (path to me as alias) & "Contents/Resources/start_server.sh"
    do shell script "bash " & quoted form of scriptPath
    display notification "Server starting..." with title "YouTube Intelligence"
end run
