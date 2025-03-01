// exporters.js
migrate((app) => {
    let collection = new Collection({
        name: "exporters",
        type: "base",
        fields: [
            {
                name: "exporter_id",
                type: "text",
                required: true,
                unique: true
            },
            {
                name: "exporter_name",
                type: "text",
                required: true
            },
            {
                name: "country_of_origin",
                type: "text",
                required: true
            },
            {
                name: "industry_focus",
                type: "text",
                required: true
            },
            {
                name: "operation_size",
                type: "text",
                required: false
            },
            {
                name: "tech_level",
                type: "text",
                required: false
            },
            {
                name: "export_frequency",
                type: "text",
                required: false
            },
            {
                name: "shipping_modalities",
                type: "text",
                required: false
            }
        ]
    })
    return app.save(collection)
}, (app) => {
    let collection = app.findCollectionByNameOrId("exporters")
    return app.delete(collection)
})
