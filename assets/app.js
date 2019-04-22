(function() {
    "use strict";
    
    /*
     * A websocket connection to the server that we can receive and send messages over.
     */
    class Session {
        constructor() {
            this.state = "disconnected";    // "disconnected", "connecting", "connected"
            this.messageCallback = null;    // invoked for incoming messages
            this.socket = null;             // websocket connection
        }
        
        // Set the callback that will be invoked when messages arrive.
        // The callback will receive the author and message parameters.
        onMessage(callback) {
            this.messageCallback = callback;
        }
        
        // Start the session by connecting to the server.
        connect() {
            if (this.state === "disconnected") {
                const protocol = window.location.protocol === "https" ? "wss" : "ws";
                const host = window.location.host;
                this.socket = new WebSocket(`${protocol}://${host}/session`);
                this.socket.addEventListener("open", event => {
                    this.state = "connected";
                    if (this.messageCallback) {
                        this.messageCallback("SYSTEM", "Connection established.");
                    }
                });
                this.socket.addEventListener("close", event => {
                    this.state = "disconnected";
                    this.socket = null;
                    
                    if (this.messageCallback) {
                        this.messageCallback("SYSTEM", `You have been disconnected.`);
                    }
                });
                this.socket.addEventListener("error", event => {
                    console.error("Error from websocket", event);
                    if (this.messageCallback) {
                        this.messageCallback("SYSTEM", "Connection error.");
                    }
                });
                this.socket.addEventListener("message", event => {
                    let data = JSON.parse(event.data);
                    if (!this.messageCallback) {
                        console.error("No message callback provided to the session.");
                        return;
                    }
                    this.messageCallback(data.author, data.message);
                });
                
                this.state = "connecting";
                if (this.messageCallback) {
                    this.messageCallback("SYSTEM", "Connecting...");
                }
            }
        }
        
        // Send a message to the chat room. It is an error to invoke this function before
        // the connection has been established.
        sendMessage(message) {
            if (this.state != "connected") {
                console.error("The session is not connected.");
                return;
            }
            
            let data = {
                type: "message",
                message: message
            };
            this.socket.send(JSON.stringify(data));
        }
    }
        
    // This reusable component renders single chat messages.
    let ChatMessage = Vue.component("ChatMessage", {
        props: ["author", "message"],
        template: `
            <div class="message" v-once>
                <span class="author">{{author}}:</span>
                <span class="content">{{message}}</span>
            </div>        
        `
    });

    let app = new Vue({
        el: "#app",
        data: {
            // The content of the message input field.
            currentMessage: "",
        },
        methods: {
            // Invoked when the user sends the current content of the input field.
            submitMessage() {
                let message = this.currentMessage.trim();
                if (message === "") {
                    return;
                }
                
                this.$emit("message", message);
            },
            
            // Resets the chat message field and focuses it.
            clearMessage() {
                this.currentMessage = "";
                this.$refs.input_bar.focus();   
            },
            
            // Append a message to the message log.
            appendMessage(author, message) {
                // (ab-)using a short lived vue instance for rendering.
                // don't leak the instance after initial rendering to save memory.
                let comp = new ChatMessage({
                    propsData: {
                        author, message
                    }
                });
                comp.$mount();
                
                let log = this.$refs.message_log;
                let elem = comp.$el;
                log.appendChild(elem);
                if (log.childElementCount > 1000) {
                    log.removeChild(log.childNodes[0]);
                }
                
                elem.scrollIntoView(true);
                
                // Instance is no longer needed.
                comp.$destroy();
            }
        }
    });
    
    let session = new Session();
    session.onMessage((author, message) => app.appendMessage(author, message));
    session.connect();
    
    app.$on("message", message => {      
        if (session.state !== "connected") {
            app.appendMessage("SYSTEM", "You are not connected.");
            return;
        }
        
        session.sendMessage(message);
        app.clearMessage();
    });
})();
