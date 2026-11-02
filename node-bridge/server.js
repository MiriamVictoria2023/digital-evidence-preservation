// Optional Node.js health-check bridge for environments that require a Node service.
// The main REST API is provided by Flask on port 5000.
const http = require('http');
const PORT = 5001;
http.createServer((req, res) => {
  res.writeHead(200, {'Content-Type':'application/json'});
  res.end(JSON.stringify({service:'evidence-node-bridge', status:'ok', api:'http://127.0.0.1:5000/api'}));
}).listen(PORT, '127.0.0.1', () => console.log(`Node bridge listening on ${PORT}`));
