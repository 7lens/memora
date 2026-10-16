import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
let checks = 0;
const check = new Proxy(assert, {
  get(target, key) {
    const value = target[key];
    return typeof value === "function"
      ? (...args) => {
          checks++;
          return value(...args);
        }
      : value;
  },
});
const [chrome, root, liveUrl] = process.argv.slice(2),
  errors = [];
const processChrome = spawn(
  chrome,
  [
    "--headless=new",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-debugging-port=0",
    `--user-data-dir=${root}/chrome`,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"] },
);
let stderr = "";
let socket;
const pending = new Map();
let id = 0;
try {
  const endpoint = await new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error("Chrome did not start.")),
      15000,
    );
    processChrome.stderr.on("data", (data) => {
      stderr += data;
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });
    processChrome.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error("Chrome stopped: " + code + " " + stderr));
    });
  });
  const origin = endpoint.replace(/^ws:/, "http:").split("/devtools/")[0];
  const target = await (
    await fetch(
      origin +
        "/json/new?" +
        encodeURIComponent(pathToFileURL(root + "/memora.html").href),
      { method: "PUT" },
    )
  ).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve) =>
    socket.addEventListener("open", resolve, { once: true }),
  );
  socket.addEventListener("message", (event) => {
    const obj = JSON.parse(event.data);
    if (obj.id && pending.has(obj.id)) {
      const p = pending.get(obj.id);
      pending.delete(obj.id);
      obj.error ? p.reject(obj.error) : p.resolve(obj.result);
    }
    if (obj.method === "Runtime.exceptionThrown")
      errors.push(obj.params.exceptionDetails.text);
  });
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const current = ++id;
      pending.set(current, { resolve, reject });
      socket.send(JSON.stringify({ id: current, method, params }));
    });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
    return r.result.value;
  };
  const ready = async () => {
    for (let n = 0; n < 80; n++) {
      if (await evaluate("Boolean(window.brainViewState)")) return;
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error("The viewer did not load.");
  };
  const act = async (expression) => {
    await evaluate(expression);
    await new Promise((r) => setTimeout(r, 50));
  };
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 960,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await ready();
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 12);
  check.ok(
    await evaluate(
      "document.querySelector('#graphGuide summary').textContent==='Graph guide'",
    ),
  );
  await act("document.querySelector('#graphGuide summary').click()");
  check.ok(
    await evaluate(
      "document.getElementById('graphGuide').open && document.getElementById('graphGuide').textContent.includes('Arrow:')",
    ),
  );
  check.ok(
    await evaluate(
      "(()=>{const p=Object.values(window.brainViewState.positions);return p.length>1&&p.every((a,i)=>p.slice(i+1).every(b=>Math.hypot(a.x-b.x,a.y-b.y)>200))})()",
    ),
  );
  check.ok(
    await evaluate(
      "[...ctx.getImageData(0,0,graph.width,graph.height).data].some((v,i)=>i%4===3&&v>0)",
    ),
  );
  await writeFile(
    root + "/desktop.png",
    Buffer.from(
      (await send("Page.captureScreenshot", { format: "png" })).data,
      "base64",
    ),
  );
  await act("document.querySelector('#memorySessions summary').click()");
  check.ok(
    await evaluate(
      "document.querySelector('#sessionList').textContent.includes('1 context calls')",
    ),
  );
  check.ok(
    await evaluate(
      "document.querySelector('#sessionList').textContent.includes('context returned')",
    ),
  );
  check.ok(
    await evaluate(
      "document.querySelector('#sessionList').textContent.includes('note returned')",
    ),
  );
  const beforePan = await evaluate("JSON.stringify(offset)");
  await send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: 500,
    y: 500,
    button: "left",
    buttons: 1,
  });
  await send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: 540,
    y: 530,
    button: "left",
    buttons: 1,
  });
  await send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: 540,
    y: 530,
    button: "left",
  });
  check.notEqual(await evaluate("JSON.stringify(offset)"), beforePan);
  await act("document.getElementById('reset').click()");
  await act(
    "window.clusterPoint=(()=>{const p=positions.get(shown[0].path),r=graph.getBoundingClientRect();return{x:r.left+offset.x+p.x*scale,y:r.top+offset.y+p.y*scale}})()",
  );
  await send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: await evaluate("window.clusterPoint.x"),
    y: await evaluate("window.clusterPoint.y"),
    button: "left",
    buttons: 1,
  });
  await send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: await evaluate("window.clusterPoint.x"),
    y: await evaluate("window.clusterPoint.y"),
    button: "left",
  });
  await new Promise((r) => setTimeout(r, 50));
  await act("document.querySelector('#details button').click()");
  check.equal(await evaluate("window.brainViewState.mode"), "notes");
  await act("document.getElementById('clusters').click()");
  await act("document.getElementById('expand').click()");
  check.equal(await evaluate("window.brainViewState.visibleNodes"), 12);
  await act("document.getElementById('listToggle').click()");
  check.equal(
    await evaluate("document.querySelectorAll('#list tbody tr').length"),
    12,
  );
  check.ok(
    await evaluate(
      "document.querySelector('#list table').scrollWidth<=document.querySelector('#list').clientWidth",
    ),
  );
  check.ok(
    await evaluate(
      "(()=>{const cells=[...document.querySelector('#list tbody tr').cells].map(x=>x.getBoundingClientRect());return cells.every((x,i)=>!i||cells[i-1].right<=x.left+1)})()",
    ),
  );
  await act("document.querySelector('#list tbody button').click()");
  check.ok(
    await evaluate(
      "document.querySelector('#details h2').textContent.length>0",
    ),
  );
  await act(
    "document.getElementById('type').value='Fact';document.getElementById('type').dispatchEvent(new Event('change'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 1);
  await act(
    "document.getElementById('type').value='';document.getElementById('type').dispatchEvent(new Event('change'));document.getElementById('query').value='safe display';document.getElementById('query').dispatchEvent(new Event('input'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 1);
  await act("document.querySelector('#list tbody button').click()");
  check.ok(
    await evaluate(
      "document.querySelector('#details h2').textContent.includes('</script>')",
    ),
  );
  check.equal(await evaluate("window.INJECTED"), undefined);
  check.equal(
    await evaluate(
      "document.querySelectorAll('#details a[href^=\"javascript:\"]').length",
    ),
    0,
  );
  await act(
    "document.getElementById('query').value='';document.getElementById('query').dispatchEvent(new Event('input'));document.getElementById('score').value='75';document.getElementById('score').dispatchEvent(new Event('change'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 0);
  await act(
    "document.getElementById('score').value='0';document.getElementById('score').dispatchEvent(new Event('change'));document.getElementById('project').value=document.getElementById('project').options[1].value;document.getElementById('project').dispatchEvent(new Event('change'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 11);
  await act(
    "document.getElementById('repository').value=document.getElementById('repository').options[1].value;document.getElementById('repository').dispatchEvent(new Event('change'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 10);
  check.equal(await evaluate("document.getElementById('subject')"), null);
  await act(
    "document.getElementById('project').value='';document.getElementById('project').dispatchEvent(new Event('change'));document.getElementById('repository').value='';document.getElementById('repository').dispatchEvent(new Event('change'));document.getElementById('state').value='settled';document.getElementById('state').dispatchEvent(new Event('change'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 1);
  await act(
    "document.getElementById('state').value='provisional';document.getElementById('state').dispatchEvent(new Event('change'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 11);
  await act(
    "document.getElementById('state').value='';document.getElementById('state').dispatchEvent(new Event('change'))",
  );
  await act(
    "document.getElementById('listToggle').click();document.getElementById('zoomIn').click();document.getElementById('reset').click()",
  );
  await send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await new Promise((r) => setTimeout(r, 100));
  check.ok(await evaluate("document.documentElement.scrollWidth<=390"));
  await writeFile(
    root + "/mobile.png",
    Buffer.from(
      (
        await send("Page.captureScreenshot", {
          format: "png",
          captureBeyondViewport: true,
        })
      ).data,
      "base64",
    ),
  );
  await act("document.getElementById('listToggle').click()");
  check.ok(
    await evaluate(
      "document.querySelector('#list table').scrollWidth<=document.querySelector('#list').clientWidth",
    ),
  );
  await send("Page.navigate", {
    url: pathToFileURL(root + "/large.html").href,
  });
  await new Promise((r) => setTimeout(r, 300));
  await ready();
  await act("document.getElementById('expand').click()");
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 10000);
  check.equal(await evaluate("window.brainViewState.visibleNodes"), 500);
  check.ok(await evaluate("window.brainViewState.visibleEdges<=2000"));
  check.ok(
    await evaluate(
      "document.getElementById('status').textContent.includes('9500 nodes')",
    ),
  );
  await act("document.getElementById('listToggle').click()");
  check.equal(
    await evaluate("document.querySelectorAll('#list tbody tr').length"),
    50,
  );
  check.ok(
    await evaluate(
      "document.querySelector('#list').textContent.includes('1–50 of 10000')",
    ),
  );
  await act(
    "document.querySelector('#list .list-pager button:last-child').click()",
  );
  check.equal(await evaluate("window.brainViewState.page"), 1);
  check.equal(
    await evaluate("document.querySelectorAll('#list tbody tr').length"),
    50,
  );
  await act(
    "document.querySelector('#list th button[data-sort=score]').click()",
  );
  check.equal(await evaluate("window.brainViewState.page"), 0);
  check.equal(
    await evaluate(
      "document.querySelector('#list tbody tr:first-child td:last-child').textContent",
    ),
    "25",
  );
  await act(
    "document.querySelector('#list th button[data-sort=score]').click()",
  );
  check.equal(
    await evaluate(
      "document.querySelector('#list tbody tr:first-child td:last-child').textContent",
    ),
    "100",
  );
  await act(
    "document.getElementById('query').value='Large node 9999';document.getElementById('query').dispatchEvent(new Event('input'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 1);
  await send("Page.navigate", {
    url: pathToFileURL(root + "/empty.html").href,
  });
  await new Promise((r) => setTimeout(r, 200));
  await ready();
  check.ok(await evaluate("!document.getElementById('empty').hidden"));
  await send("Page.navigate", {
    url: pathToFileURL(root + "/external.html").href,
  });
  await ready();
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 2);
  await act(
    "document.getElementById('expand').click();document.getElementById('listToggle').click()",
  );
  await act(
    "document.getElementById('type').value='ExternalReference';document.getElementById('type').dispatchEvent(new Event('change'))",
  );
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 1);
  await act("document.querySelector('#list tbody button').click()");
  check.ok(
    await evaluate(
      "document.querySelector('#details').textContent.includes('Unchecked in this local view. Resolve this reference through its connected service.')",
    ),
  );
  check.ok(
    await evaluate(
      "document.querySelector('#details').textContent.includes('Observed revision: 4')",
    ),
  );
  check.ok(
    await evaluate(
      "document.querySelector('#details').textContent.includes('Platform guidance')",
    ),
  );
  await send("Page.navigate", { url: liveUrl });
  await new Promise((resolve) => setTimeout(resolve, 200));
  await ready();
  check.equal(await evaluate("window.brainViewState.live"), true);
  const projectCluster = await evaluate(
    "Object.keys(window.brainViewState.positions).find(path=>path.startsWith('project:'))",
  );
  const originalPosition = await evaluate(
    `window.brainViewState.positions[${JSON.stringify(projectCluster)}]`,
  );
  for (let attempt = 0; attempt < 80; attempt++) {
    if (await evaluate("window.brainViewState.matchingNotes === 13")) break;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  check.equal(await evaluate("window.brainViewState.matchingNotes"), 13);
  check.deepEqual(
    await evaluate(
      `window.brainViewState.positions[${JSON.stringify(projectCluster)}]`,
    ),
    originalPosition,
  );
  check.ok(
    await evaluate(
      "document.getElementById('time').textContent.startsWith('Live')",
    ),
  );
  const waitFor = async (expression) => {
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await evaluate(expression)) return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("The workflow did not reach: " + expression);
  };
  await act("document.getElementById('add-knowledge').click()");
  await act(
    `document.querySelector('[aria-label="Name"]').value='Browser service';document.querySelector('[aria-label="Description"]').value='Service context for another chat.';document.querySelector('#details form').requestSubmit()`,
  );
  await waitFor(
    "document.querySelector('#details h2')?.textContent === 'Browser service'",
  );
  await act(
    "Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Read full note').click()",
  );
  await waitFor(
    "document.querySelector('#details').textContent.includes('Service context for another chat.')",
  );
  await act(
    "Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Record observation').click()",
  );
  await act(
    `document.querySelector('[aria-label="Name"]').value='Browser support';document.querySelector('[aria-label="Property"]').value='support_status';document.querySelector('[aria-label="Value"]').value='supported';document.querySelector('[aria-label="Sources (one reference per line)"]').value='https://example.org/support';document.querySelector('#details form').requestSubmit()`,
  );
  await waitFor(
    "document.querySelector('#details h2')?.textContent === 'Browser support'",
  );
  await act(
    "Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Propose or review sharing').click()",
  );
  await waitFor(
    "Boolean(document.querySelector('[aria-label=\"Destination space\"]'))",
  );
  await act(
    `document.querySelector('[aria-label="Destination space"]').value='team';document.querySelector('[aria-label="Reason to share"]').value='Share a sourced status.';document.querySelector('[aria-label="Shared text"]').value='Service has reported support.';document.querySelector('#details form').requestSubmit()`,
  );
  await waitFor(
    "Array.from(document.querySelectorAll('#details button')).some(b=>b.textContent==='Approve this projection')",
  );
  check.ok(
    await evaluate(
      "document.querySelector('#details pre').textContent.includes('Service has reported support.')",
    ),
  );
  await act(
    "Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Approve this projection').click()",
  );
  await waitFor(
    `fetch('/api/data').then(r=>r.json()).then(d=>d.nodes.find(n=>n.title==='Browser support')?.publication.state==='approved')`,
  );
  check.ok(await evaluate("document.documentElement.scrollWidth<=390"));
  // Portal layout and keyboard access.
  check.equal(
    await evaluate("document.documentElement.dataset.theme"),
    "light",
  );
  check.equal(await evaluate("document.querySelectorAll('.metric').length"), 4);
  await act(
    "document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'/',bubbles:true}))",
  );
  check.equal(await evaluate("document.activeElement.id"), "query");
  await act(
    "document.getElementById('query').blur();select(data.nodes.find(n=>n.title==='Browser service'))",
  );
  await waitFor(
    "document.querySelector('#pane-note .note-content').textContent.includes('Service context for another chat.')",
  );
  check.ok(
    await evaluate("document.querySelector('#pane-note').hidden===false"),
  );
  await act(
    "document.getElementById('tab-note').focus();document.getElementById('tab-note').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))",
  );
  check.equal(
    await evaluate(
      "document.getElementById('tab-evidence').getAttribute('aria-selected')",
    ),
    "true",
  );
  await act(
    "document.getElementById('tab-note').click();Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Edit note').click()",
  );
  await waitFor("Boolean(document.querySelector('[aria-label=\"Content\"]'))");
  const newBody =
    "## Support overview\n\nUse **approved** source evidence.\n\n<script>window.RENDERED_INJECTION=1</script>\n[unsafe](javascript:alert(1))";
  await act(
    `document.querySelector('[aria-label="Content"]').value=${JSON.stringify(newBody)};document.querySelector('[aria-label="Reason for this change"]').value='Improve the knowledge summary.'`,
  );
  await evaluate(
    "(()=>{const n=data.nodes.find(n=>n.title==='Browser service');window.editPath=n.path;return action({action:'edit',key:n.path,revision:n.revision,title:n.title,body:'A concurrent source edit.',reason:'Test concurrent writes.'})})()",
  );
  check.equal(
    await evaluate("document.querySelector('[aria-label=\"Content\"]').value"),
    newBody,
  );
  await act("document.querySelector('#details form').requestSubmit()");
  await waitFor(
    "document.querySelector('#details [role=status]').textContent.includes('revision')",
  );
  check.equal(
    await evaluate(
      "fetch('/api/note?path='+encodeURIComponent(window.editPath)).then(r=>r.json()).then(n=>n.body.trim())",
    ),
    "A concurrent source edit.",
  );
  await act(
    "Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Cancel').click()",
  );
  await act(
    "Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Edit note').click()",
  );
  await waitFor("Boolean(document.querySelector('[aria-label=\"Content\"]'))");
  await act(
    `document.querySelector('[aria-label="Content"]').value=${JSON.stringify(newBody)};document.querySelector('[aria-label="Reason for this change"]').value='Review the current revision.';document.querySelector('#details form').requestSubmit()`,
  );
  await waitFor(
    "document.querySelector('#details h2')?.textContent === 'Browser service'",
  );
  await waitFor(
    "document.querySelector('.note-content strong')?.textContent==='approved'",
  );
  check.equal(
    await evaluate("document.querySelector('.note-content h2').textContent"),
    "Support overview",
  );
  check.equal(
    await evaluate(
      "document.querySelectorAll('.note-content script,.note-content a[href^=\"javascript:\"]').length",
    ),
    0,
  );
  check.equal(await evaluate("window.RENDERED_INJECTION"), undefined);
  await evaluate(
    "(()=>{const n=byId.get(window.editPath);return action({action:'edit',key:n.path,revision:n.revision,title:n.title,body:'## Support overview\\n\\nUse **approved** source evidence.\\n\\n- Review vendor support dates.\\n- Record changes as observations.\\n\\nKeep this context available for the next chat.',reason:'Keep a readable support summary.'})})()",
  );
  await waitFor(
    "document.querySelector('.note-content strong')?.textContent==='approved'",
  );
  await act("document.getElementById('tab-history').click()");
  check.ok(
    await evaluate(
      "document.getElementById('pane-history').textContent.includes('Test concurrent writes.')",
    ),
  );
  await act(
    "document.getElementById('tab-note').click();document.getElementById('themeToggle').click()",
  );
  check.equal(await evaluate("document.documentElement.dataset.theme"), "dark");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 960,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await new Promise((resolve) => setTimeout(resolve, 100));
  await act(
    "document.getElementById('expand').click();document.getElementById('reset').click()",
  );
  await writeFile(
    root + "/portal-dark.png",
    Buffer.from(
      (await send("Page.captureScreenshot", { format: "png" })).data,
      "base64",
    ),
  );
  await send("Page.navigate", { url: liveUrl });
  await new Promise((resolve) => setTimeout(resolve, 200));
  await ready();
  check.equal(await evaluate("document.documentElement.dataset.theme"), "dark");
  await act(
    "document.getElementById('themeToggle').click();select(data.nodes.find(n=>n.title==='Browser service'))",
  );
  await waitFor(
    "document.querySelector('.note-content strong')?.textContent==='approved'",
  );
  await act(
    "document.getElementById('expand').click();document.getElementById('reset').click()",
  );
  await writeFile(
    root + "/portal-desktop.png",
    Buffer.from(
      (await send("Page.captureScreenshot", { format: "png" })).data,
      "base64",
    ),
  );
  // Editing approved content must invalidate the publication review.
  await act(
    "select(data.nodes.find(n=>n.title==='Browser support'));Array.from(document.querySelectorAll('#details button')).find(b=>b.textContent==='Edit note').click()",
  );
  await waitFor("Boolean(document.querySelector('[aria-label=\"Content\"]'))");
  await act(
    "document.querySelector('[aria-label=\"Content\"]').value='Changed support claim.';document.querySelector('[aria-label=\"Reason for this change\"]').value='Correct the claim.';document.querySelector('#details form').requestSubmit()",
  );
  await waitFor(
    "data.nodes.find(n=>n.title==='Browser support')?.publication.state==='stale'",
  );
  check.ok(
    await evaluate(
      "document.querySelector('#details').textContent.includes('Sharing: stale')",
    ),
  );
  // Capture a knowledge note, not only an inventory-like subject.
  await act(
    "document.getElementById('add-knowledge').click();document.querySelector('[aria-label=\"Record type\"]').value='Decision';document.querySelector('[aria-label=\"Record type\"]').dispatchEvent(new Event('change'));document.querySelector('[aria-label=\"Name\"]').value='Browser decision';document.querySelector('[aria-label=\"Description\"]').value='Keep the durable decision.';document.querySelector('#details form').requestSubmit()",
  );
  await waitFor(
    "document.querySelector('#details h2')?.textContent==='Browser decision'",
  );
  check.equal(
    await evaluate("data.nodes.find(n=>n.title==='Browser decision').type"),
    "Decision",
  );
  await act(
    "document.getElementById('quickView').value='review';document.getElementById('quickView').dispatchEvent(new Event('change'))",
  );
  check.ok(
    await evaluate(
      "filtered.every(n=>['provisional','disputed'].includes(n.state))",
    ),
  );
  await act("document.getElementById('clearFilters').click()");
  check.equal(
    await evaluate("window.brainViewState.matchingNotes"),
    await evaluate("data.nodes.length"),
  );
  await act(
    "select(data.nodes.find(n=>n.title==='Browser decision'));document.getElementById('tab-relations').click()",
  );
  await send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await new Promise((resolve) => setTimeout(resolve, 100));
  check.ok(await evaluate("document.documentElement.scrollWidth<=390"));
  await writeFile(
    root + "/portal-mobile.png",
    Buffer.from(
      (
        await send("Page.captureScreenshot", {
          format: "png",
          captureBeyondViewport: true,
        })
      ).data,
      "base64",
    ),
  );
  await act(
    "document.getElementById('space').value='team';document.getElementById('space').dispatchEvent(new Event('change'))",
  );
  await new Promise((resolve) => setTimeout(resolve, 200));
  await ready();
  await waitFor("window.brainViewState.matchingNotes === 0");
  check.deepEqual(errors, []);
  console.log(
    JSON.stringify(
      {
        passed: true,
        checks,
        largeNodes: 10000,
        browserErrors: errors,
        screenshots: [
          root + "/desktop.png",
          root + "/mobile.png",
          root + "/portal-desktop.png",
          root + "/portal-dark.png",
          root + "/portal-mobile.png",
        ],
      },
      null,
      2,
    ),
  );
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  socket?.close();
  processChrome.kill("SIGTERM");
}
