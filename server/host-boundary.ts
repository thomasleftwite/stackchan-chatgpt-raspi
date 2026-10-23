import {isIPv4} from 'node:net';
import {hotspotPeerAllowed} from './gemini-server.js';

/** Same AP/explicit fixture boundary for conversation and device audition hosts. */
export function hostBoundary(value:unknown) {
  if(!value || typeof value!=='object') throw new Error('Invalid host boundary');
  const v=value as {host:string;port:number;subnet:string;fixture?:boolean};
  const ip=v.host?.split('.').map(Number);
  const local=v.fixture===true && v.host==='127.0.0.1' && v.subnet==='127.0.0.1/32';
  if((v.fixture!==undefined && typeof v.fixture!=='boolean') || !isIPv4(v.host) ||
      !(local || ip[0]===10 || (ip[0]===172 && ip[1]!>=16 && ip[1]!<=31) || (ip[0]===192 && ip[1]===168)) ||
      !Number.isInteger(v.port) || v.port<1024 || v.port>65535 || !v.subnet || !hotspotPeerAllowed(v.host,v.subnet))
    throw new Error('Invalid host boundary');
  return {host:v.host,port:v.port,subnet:v.subnet,fixture:v.fixture===true};
}
