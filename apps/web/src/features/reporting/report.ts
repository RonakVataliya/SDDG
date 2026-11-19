/** Feature 3.3: shows the project report outside the app's own DOM, in a new tab or in a hidden iframe for printing. */

/** Opens the report in a new tab. The tab opens before the request, while the click still counts as a user gesture, so
 *  pop-up blockers let it through; it is pointed at the report once that has loaded. */
export async function openReport(load: () => Promise<Blob>) {
  const tab = window.open('', '_blank')
  if (!tab) throw new Error('Your browser blocked the new tab. Allow pop-ups for this site and try again.')
  tab.opener = null // the report runs no scripts, but it has no reason to reach back into the app
  try {
    const url = URL.createObjectURL(await load())
    tab.location.href = url
    // shortcut: a fixed delay instead of the tab's load event (not observable across its navigation); a reload of the tab after a minute shows nothing
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (e) {
    tab.close()
    throw e
  }
}

/** Prints the report from a hidden iframe, so the print dialog ("Save as PDF") prints exactly the report, not the app. */
export async function printReport(load: () => Promise<Blob>) {
  const url = URL.createObjectURL(await load())
  const frame = document.createElement('iframe')
  // No allow-scripts: allow-same-origin only lets this page call the frame's print(), allow-modals lets that open the dialog.
  frame.setAttribute('sandbox', 'allow-same-origin allow-modals')
  frame.setAttribute('aria-hidden', 'true')
  frame.tabIndex = -1
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  const done = () => {
    frame.remove()
    URL.revokeObjectURL(url)
  }
  await new Promise<void>((resolve, reject) => {
    frame.onload = () => {
      try {
        frame.contentWindow!.addEventListener('afterprint', done, { once: true })
        frame.contentWindow!.print()
        resolve()
      } catch (e) {
        done()
        reject(e)
      }
    }
    frame.src = url
    document.body.appendChild(frame)
  })
}
