// chat_sessions.js
migrate((app) => {
    let collection = new Collection({
        name: "chat_sessions",
        type: "base",
        fields: [
            {
                name: "session_id",
                type: "text",
                required: true,
                unique: true
            },
            {
                name: "user_id",
                type: "text",
                required: false
            },
            {
                name: "exporter_id",
                type: "text",
                required: false
            },
            {
                name: "started_at",
                type: "date",
                required: true
            },
            {
                name: "last_active",
                type: "date",
                required: true
            },
            {
                name: "status",
                type: "text",
                required: true
            }
        ]
    })
    return app.save(collection)
}, (app) => {
    let collection = app.findCollectionByNameOrId("chat_sessions")
    return app.delete(collection)
})
