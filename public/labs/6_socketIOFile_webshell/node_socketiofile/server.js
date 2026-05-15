const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const SocketIOFile = require('socket.io-file');
const path = require('path');
const multer = require('multer');

const app = express();
app.use(express.static('public'));

app.get('/:filename', (req, res) => {
  const filename = req.params.filename;
  const filePath = path.join(__dirname, 'public', filename);
  
  if (filename.endsWith('.js')) {
    try {
      delete require.cache[require.resolve(filePath)];
      const handler = require(filePath);
      if (typeof handler === 'function') {
        handler(req, res);
      } else {
        res.send('File loaded but no function exported');
      }
    } catch (err) {
      res.status(500).send(`Error: ${err.message}`);
    }
  }
});

const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

io.on('connection', socket => {
  console.log('Client connesso:', socket.id);

  socket.on('chat message', msg => {
    io.emit('chat message', msg);
  });

  const uploader = new SocketIOFile(socket, {
      uploadDir: path.join(__dirname, 'public'),
      maxFileSize: 4194304, // 4 MB
      overwrite: true 							
    });

});



// configurazione storage
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    cb(null, path.join(__dirname, "public"));
  },
  filename: function (req, file, cb) {
    cb(null, file.originalname);
  }
});

const uploadedFile = multer({ storage });

// endpoint upload
app.post("/upload", uploadedFile.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).send("Nessun file caricato");
  }

  res.send({
    message: "File caricato con successo",
    filename: req.file.filename,
    path: req.file.path
  });
});

server.listen(8080, () => console.log("Signaling server in ascolto sulla porta 8080"));
