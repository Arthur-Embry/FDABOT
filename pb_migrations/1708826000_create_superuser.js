// pb_migrations/1708826000_create_superuser.js

migrate((app) => {
    const superusers = app.findCollectionByNameOrId("_superusers")
    
    const record = new Record(superusers)
    record.set("email", "admin@example.com")
    record.set("password", "password123")
    
    app.save(record)
    
    console.log("Superuser admin@example.com created via migration")
}, (app) => {
    try {
        const record = app.findAuthRecordByEmail("_superusers", "admin@example.com")
        app.delete(record)
    } catch {
        // silent errors (probably already deleted)
    }
})