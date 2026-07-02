import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, ChildProcess } from 'child_process';
import { JarvisBridge } from './bridge';

let backendProcess: ChildProcess | null = null;

export function activate(context: vscode.ExtensionContext) {
    console.log('JARVIS extension activated');

    // Auto-start the FastAPI backend
    const workspaceRoot = path.join(context.extensionPath, '..');
    const pythonExe = path.join(workspaceRoot, '.venv', 'Scripts', 'python.exe');
    
    if (fs.existsSync(pythonExe)) {
        console.log('Starting JARVIS backend...');
        backendProcess = spawn(pythonExe, ['-m', 'uvicorn', 'jarvis.main:app', '--host', '127.0.0.1', '--port', '8000'], {
            cwd: workspaceRoot,
            shell: false
        });

        backendProcess.stdout?.on('data', (data) => console.log(`Backend: ${data}`));
        backendProcess.stderr?.on('data', (data) => console.error(`Backend Err: ${data}`));
        
        backendProcess.on('close', (code) => {
            console.log(`Backend process exited with code ${code}`);
            backendProcess = null;
        });
    } else {
        vscode.window.showErrorMessage('JARVIS Backend: Could not find .venv/Scripts/python.exe. Please ensure the virtual environment is set up.');
    }

    // Start WebSocket bridge
    const bridge = new JarvisBridge();

    let disposable = vscode.commands.registerCommand('jarvis.openChat', () => {
        const panel = vscode.window.createWebviewPanel(
            'jarvisChat',
            'JARVIS',
            vscode.ViewColumn.Two,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'dist', 'webview'))]
            }
        );

        // Get the local path to main script run in the webview, then convert it to a uri we can use in the webview.
        const scriptPathOnDisk = vscode.Uri.file(
            path.join(context.extensionPath, 'dist', 'webview', 'App.js')
        );
        const scriptUri = panel.webview.asWebviewUri(scriptPathOnDisk);
        
        // CSS
        const stylePathOnDisk = vscode.Uri.file(
            path.join(context.extensionPath, 'dist', 'webview', 'index.css')
        );
        const styleUri = panel.webview.asWebviewUri(stylePathOnDisk);

        panel.webview.html = getWebviewContent(scriptUri, styleUri);
        
        // Relay messages between webview and backend bridge
        panel.webview.onDidReceiveMessage(
            message => {
                bridge.sendMessage(message);
            },
            undefined,
            context.subscriptions
        );

        bridge.onMessage((msg) => {
            panel.webview.postMessage(msg);
        });
    });

    context.subscriptions.push(disposable);
}

function getWebviewContent(scriptUri: vscode.Uri, styleUri: vscode.Uri) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS</title>
    <link rel="stylesheet" href="${styleUri}">
</head>
<body>
    <div id="root"></div>
    <script type="module" src="${scriptUri}"></script>
</body>
</html>`;
}

export function deactivate() {
    if (backendProcess) {
        console.log('Shutting down JARVIS backend...');
        backendProcess.kill();
        backendProcess = null;
    }
}
