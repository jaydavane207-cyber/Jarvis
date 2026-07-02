export class JarvisBridge {
    constructor() {
        console.log("Bridge initialized in pass-through mode.");
    }

    public sendMessage(message: any) {
        // Handled directly by the Webview now
    }

    public onMessage(callback: (msg: any) => void) {
        // Handled directly by the Webview now
    }
}