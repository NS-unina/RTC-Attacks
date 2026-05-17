const express = require("express");
const http = require('http');
const mongoose = require('mongoose');
const {spawn, exec} = require("child_process")
const fs = require("fs");
const path = require("path");
const util = require("util");
const execAsync = util.promisify(exec);

const app = express();
app.use(express.static("public"))
app.use(express.json())

// Load scenario metadata from JSON at startup.
async function loadScenarios() {
  try {
    // Previous implementation kept for traceability:
    // const count = await Scenario.countDocuments();
    // if (count === 0) { await Scenario.insertMany(scenarios); }
    // Change rationale: upserts keep scenario metadata in sync when IDs are split or edited.
    const dataPath = path.join(__dirname, "database", "scenarios.json");
    const rawData = fs.readFileSync(dataPath, "utf8");
    const scenarios = JSON.parse(rawData);

    await Scenario.bulkWrite(scenarios.map(({ _id, ...scenario }) => ({
      updateOne: {
        filter: { id: scenario.id },
        update: { $set: scenario },
        upsert: true
      }
    })));
  } catch (err) {
    console.error("Error:", err.message);
  }
}

// Wait until the database connection is ready.
async function connectMongoWithRetry() {
  while (true) {
    try {
      await mongoose.connect(
        "mongodb://root:example@localhost:27017/rtc_attacks?authSource=admin"
      );
      console.log("Mongo connected");
      break;
    } catch (err) {
      console.log("Mongo not ready, retry in 3s...");
      await new Promise(r => setTimeout(r, 3000));
    }
  }
}

// Build and start the main containers, connect to MongoDB, and load scenarios.
async function start(){
    console.log("Starting containers...");
    await execAsync(`make build start`);
    console.log("Connecting...");
    await connectMongoWithRetry();
    await loadScenarios();
    server.listen(8888, () => console.log("Server listen on port 8888"));
}

function escape(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function labPath(folder) {
    if (!/^[A-Za-z0-9_.-]+$/.test(folder || "")) {
        throw new Error("Invalid lab folder");
    }

    const resolved = path.resolve(__dirname, "public", "labs", folder);
    const labsRoot = path.resolve(__dirname, "public", "labs");

    if (!resolved.startsWith(labsRoot + path.sep)) {
        throw new Error("Invalid lab folder");
    }

    return resolved;
}

function makeEnv(req) {
    const instance = String(req.body.instance || req.body.stack || "default");

    if (!/^[A-Za-z0-9_.-]+$/.test(instance)) {
        throw new Error("Invalid instance name");
    }

    return {
        ...process.env,
        INSTANCE: instance
    };
}

function streamMake(res, cwd, args, env) {
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader("Transfer-Encoding", "chunked");

    const stream = spawn("make", args, { cwd, env });

    stream.stdout.on("data", (chunk) => {
        res.write(chunk.toString());
    });

    stream.stderr.on("data", (chunk) => {
        res.write(chunk.toString());
    });

    stream.on("close", (code) => {
        if (code !== 0) {
            res.write(`\n[process exited with code ${code}]\n`);
        }
        res.end();
    });
}

const scenarioSchema = new mongoose.Schema({
    id: Number,
    name: String,
    description: String,
    steps: String,
    containers: Array
});

const Scenario = mongoose.model("scenario", scenarioSchema);

const server = http.createServer(app)

app.get("/scenarios",async (req, res)=>{
    try {
        const scenarios = await Scenario.find().sort({id: 1});

        const names = scenarios.map(s => s.name);
        const ids = scenarios.map(s => s.id);

        return res.json({names: names, ids: ids});    
    } catch(err){
        return res.status(500).json({ok: false, err: err.message});
    }
})

app.get("/scenario/:id", async(req, res) => {
    const id = parseInt(req.params.id);
    try {
        const scenario = await Scenario.findOne({id: id})

        if (!scenario) {
            return res.status(404).json({ error: "Scenario not found" });
        }

        return res.json({name: scenario.name, description: scenario.description, steps: scenario.steps});
    } catch(err){
        return res.status(500).json({ok: false, err: err.message});
    }
})

app.post("/make-start", async(req, res) => {
    try {
        const folder = req.body.folder;
        await execAsync(`make start`);
        streamMake(res, labPath(folder), ["start"], makeEnv(req));
    } catch (err) {
        return res.status(400).send(err.message);
    }
})

app.post("/make-stop", async(req, res) => {
    try {
        const folder = req.body.folder;
        streamMake(res, labPath(folder), ["stop"], makeEnv(req));
    } catch (err) {
        return res.status(400).send(err.message);
    }
})

app.get("/search", async(req, res) => {
    const name = escape(req.query.name);
    try {
        const scenarios = await Scenario.find({ name:{ $regex: name, $options: "i" }}).sort({id: 1});;
        if (scenarios.length === 0) {
            return res.status(404).json({ error: "Scenario not found" });
        }
        return res.json(scenarios)
    } catch(err){
        return res.status(500).json({ok: false, err: err.message});
    }
})

app.post("/build-all", async(req, res) => {
    const folder = req.body.folder;
    const elements = req.body.elements;
    
    try {
        const services = String(elements || "")
            .replaceAll(",", " ")
            .split(/\s+/)
            .filter(Boolean);

        if (!services.every(service => /^[A-Za-z0-9_.-]+$/.test(service))) {
            throw new Error("Invalid image/service name");
        }

        streamMake(res, labPath(folder), ["build", `SERVICE=${services.join(" ")}`], makeEnv(req));
    } catch (err) {
        return res.status(400).send(err.message);
    }
})

app.post("/build", async(req, res) => {
    const image = req.body.image;
    const folder = req.body.folder;

    try {
        if (!/^[A-Za-z0-9_.-]+$/.test(image || "")) {
            throw new Error("Invalid image/service name");
        }

        streamMake(res, labPath(folder), ["build", `SERVICE=${image}`], makeEnv(req));
    } catch (err) {
        return res.status(400).send(err.message);
    }
})

app.post("/make-auto-attack", async(req, res) => {
    try {
        const folder = req.body.folder;
        const scenario = String(req.body.scenario || "");
        const args = ["auto-attack"];

        if (scenario) {
            args.push(`SCENARIO=${scenario}`);
        }

        streamMake(res, labPath(folder), args, makeEnv(req));
    } catch (err) {
        return res.status(400).send(err.message);
    }
})

app.post("/images-to-build", async(req, res) =>{
    const id = req.body.id;

    try {
        const scenario = await Scenario.findOne({id: id})
        const containers = scenario.containers;

        if (!scenario) {
            return res.status(404).json({ error: "Scenario not found" });
        }

        exec(`docker images --format "{{.Repository}}"`, (err, stdout, stderr) => {
            if (err) {
                return res.status(500).json({ ok: false, err: err.message });
            }

            const dockerImages = stdout
                .split("\n")
                .map(i => i.trim())
                .filter(Boolean);

            const dockerSet = new Set(dockerImages);

            const containersToSend = containers.filter(img => !dockerSet.has(img));

            res.json({ containers: containersToSend });
        });

    } catch (err) {
        return res.status(500).json({ok: false, err: err.message});
    }
})

start()

async function shutdown() {
  try {
    console.log("Stopping containers...");

    exec("make stop", (err) => {
      if (err) {
        console.error("Error:", err);
      } 
      process.exit(0);
    });

  } catch (err) {
    console.error("Error:", err);
    process.exit(1);
  }
};

process.on("SIGINT", shutdown);
