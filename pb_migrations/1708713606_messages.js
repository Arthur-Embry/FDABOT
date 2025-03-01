// chat_messages.js
migrate((app) => {
    let collection = new Collection({
        name: "chat_messages",
        type: "base",
        fields: [
            {
                name: "session_id",
                type: "text",
                required: true
            },
            {
                name: "message_id",
                type: "text",
                required: true,
                unique: true
            },
            {
                name: "role",
                type: "text",
                required: true
            },
            {
                name: "content",
                type: "text",
                required: true
            },
            {
                name: "timestamp",
                type: "date",
                required: true
            },
            {
                name: "tool_use",
                type: "json",
                required: false
            }
        ]
    })
    return app.save(collection)
}, (app) => {
    let collection = app.findCollectionByNameOrId("chat_messages")
    return app.delete(collection)
})