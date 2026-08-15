/** Keep PNG export without shipping a charting runtime. */
export async function downloadPlotPng(element: HTMLElement, fileName: string): Promise<void> {
  const svg = element.querySelector('svg')
  if (!svg) throw new Error('No hay una grafica SVG para exportar.')
  const source = new XMLSerializer().serializeToString(svg)
  const blob = new Blob([source], { type: 'image/svg+xml' })
  const url = URL.createObjectURL(blob)
  try {
    const image = new Image()
    image.src = url
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('No se pudo rasterizar la grafica.'))
    })
    const canvas = document.createElement('canvas')
    canvas.width = 1440
    canvas.height = 900
    const context = canvas.getContext('2d')
    if (!context) throw new Error('El navegador no permite exportar PNG.')
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    const png = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (!png) throw new Error('El navegador no genero un PNG.')
    const downloadUrl = URL.createObjectURL(png)
    const anchor = document.createElement('a')
    anchor.href = downloadUrl
    anchor.download = fileName
    anchor.click()
    URL.revokeObjectURL(downloadUrl)
  } finally {
    URL.revokeObjectURL(url)
  }
}
