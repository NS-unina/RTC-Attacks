const express = require("express")
const http = require("http")
const mongoose = require("mongoose")

const app = express()
app.use(express.static('public'))
app.use(express.json())

// Previous implementation kept for traceability:
// mongoose.connect("mongodb://root:example@localhost:27017/rtc_attacks?authSource=admin")
// Change rationale: the lab now owns an isolated MongoDB service per Compose project.
mongoose.connect(process.env.MONGO_URL || "mongodb://root:example@mongo:27017/rtc_attacks?authSource=admin")

const server = http.createServer(app);

const utenteSchema = new mongoose.Schema({
    username: String,
    password: String
});

const User = mongoose.model('nosqli_user', utenteSchema);

async function seedDefaultUser() {
    // A deterministic user keeps the NoSQLi auto-attack reproducible in isolated stacks.
    await User.updateOne(
        { username: "Mario" },
        { $setOnInsert: { username: "Mario", password: "Rossi" } },
        { upsert: true }
    ).exec();
}

app.get("/config.js", (req, res) => {
    res.type("application/javascript");
    res.send(`window.__LAB_CONFIG__ = ${JSON.stringify({
        vdoUrl: process.env.VDONINJA_PUBLIC_URL || "http://localhost:18080"
    })};`);
});

app.post("/login", async (req, res) => {
    const {username, password} = req.body;

    const user = await User.findOne({username, password}).exec()
    if(!user){
        return res.status(404).send('User not found')
    } 
    
    return res.status(200).send('Welcome');
    
})

mongoose.connection.once("open", () => {
    seedDefaultUser()
        .then(() => server.listen(9000, () => console.log('Server listen on 9000')))
        .catch(err => {
            console.error("Seed error:", err.message);
            process.exit(1);
        });
});
