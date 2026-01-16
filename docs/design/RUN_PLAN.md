# Run plan
We will be using Docker.

## Container Structure
* `cloudflared` - Responsible for creating a Cloudflare Tunnel to expose this service on my domain `https://qecomp.vmd1.dev`
* `vex-tm-manager-tools` - Master container running this application. Will be run in a custom docker network `cf` in order to allow only `cloudflared` to interact with it.

## Access
* The service will be placed behind the CF Proxy, to protect against attacks
* The service will be IP Restricted, with only the School's IP Block being allowed to access it.
    * This will allow the classroom desktops to freely access it, without any authentication needing to be done on any device

## Errors
They will be displayed on the server logs page