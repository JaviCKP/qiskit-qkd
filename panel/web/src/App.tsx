import { QueryClientProvider } from '@tanstack/react-query'

import { PanelShell } from '@/app/PanelShell'
import { PanelErrorBoundary } from '@/app/PanelErrorBoundary'
import { queryClient } from '@/app/queryClient'

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PanelErrorBoundary>
        <PanelShell />
      </PanelErrorBoundary>
    </QueryClientProvider>
  )
}

export default App
