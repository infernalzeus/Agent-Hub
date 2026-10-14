'use strict';
process.chdir(__dirname);
const assert = require('node:assert/strict');
const { rotate, matrix } = require('./assets/agent-hub-globe.js');
const q = new Float64Array([0, 0, 0, 1]), m = new Float64Array(9);
let seed = 93717, maxError = 0, maxDetError = 0;
function random() { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; }
for (let i = 0; i < 10000; i++) {
  let x=random()*2-1,y=random()*2-1,z=random()*2-1;
  const n=Math.hypot(x,y,z); rotate(q,x/n,y/n,z/n,(random()-.5)*.35); matrix(q,m);
  for(let a=0;a<3;a++) for(let b=0;b<3;b++) {
    const dot=m[a*3]*m[b*3]+m[a*3+1]*m[b*3+1]+m[a*3+2]*m[b*3+2];
    maxError=Math.max(maxError,Math.abs(dot-(a===b?1:0)));
  }
  const det=m[0]*(m[4]*m[8]-m[5]*m[7])-m[1]*(m[3]*m[8]-m[5]*m[6])+m[2]*(m[3]*m[7]-m[4]*m[6]);
  maxDetError=Math.max(maxDetError,Math.abs(det-1));
}
assert(maxError<1e-6); assert(maxDetError<1e-6);
console.log(JSON.stringify({rotations:10000,maxOrthonormalError:maxError,maxDeterminantError:maxDetError}));

