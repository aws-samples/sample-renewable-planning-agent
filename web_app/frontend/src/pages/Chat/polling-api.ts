const API_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '');

export class AssetPollingService {
  private intervalId: number | null = null;
  private currentProjectId: string | null = null;
  private onAssetsUpdate: ((assets: any) => void) | null = null;
  private lastAssetHash: string | null = null;

  constructor() {}

  startPolling(
    projectId: string,
    onAssetsUpdate: (assets: any) => void,
    intervalMs: number = 5000
  ) {
    this.stopPolling();
    
    this.currentProjectId = projectId;
    this.onAssetsUpdate = onAssetsUpdate;
    
    console.log(`Starting asset polling for project ${projectId} every ${intervalMs}ms`);
    
    // Initial fetch
    this.fetchAssets();
    
    // Set up polling
    this.intervalId = window.setInterval(() => {
      console.log(`Polling assets for project ${this.currentProjectId}`);
      this.fetchAssets();
    }, intervalMs);
  }

  stopPolling() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.currentProjectId = null;
    this.onAssetsUpdate = null;
    this.lastAssetHash = null;
  }

  private async fetchAssets() {
    if (!this.currentProjectId) return;

    try {
      const response = await fetch(`${API_URL}/projects/${this.currentProjectId}/assets`);
      if (!response.ok) {
        console.error('Failed to fetch assets:', response.status);
        return;
      }

      const assets = await response.json();
      
      // Create a simple hash to detect changes
      const assetHash = JSON.stringify(assets);
      
      // Only update if assets have changed and callback exists
      if (assetHash !== this.lastAssetHash && this.onAssetsUpdate) {
        console.log(`Assets changed for project ${this.currentProjectId}, updating UI`);
        this.lastAssetHash = assetHash;
        try {
          this.onAssetsUpdate(assets);
        } catch (error) {
          console.error('Error calling onAssetsUpdate callback:', error);
        }
      }
    } catch (error) {
      console.error('Error fetching assets:', error);
    }
  }

  // Method to manually trigger asset fetch
  async requestAssets(projectId: string) {
    if (projectId !== this.currentProjectId) {
      this.currentProjectId = projectId;
      this.lastAssetHash = null; // Reset hash for new project
    }
    
    if (!this.onAssetsUpdate) {
      console.warn('No callback set for requestAssets');
      return;
    }
    
    await this.fetchAssets();
  }
}

// Keep the original HTTP streaming for chat
export const streamChatMessage = async (
    message: string,
    onChunk: (chunk: string, subagent?: boolean, subagentName?: string) => void,
    _onReasoning?: (reasoning: string) => void,
    projectId?: string,
    isFirstMessage?: boolean,
    _onToolEvent?: (event: { type: string; content: string; tool_name?: string }) => void
) => {
    try {
        const body: any = { message };
        if (projectId) {
            body.project_id = projectId;
        }
        if (isFirstMessage !== undefined) {
            body.is_first_message = isFirstMessage;
        }

        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) return;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n').filter(line => line.trim());
            
            for (const line of lines) {
                try {
                    const data = JSON.parse(line);
                    if (data.type === 'response') {
                        onChunk(data.content, data.subagent, data.subagent_name);
                    }
                } catch (e) {
                    console.error('Failed to parse chunk:', e, 'Raw line:', line);
                }
            }
        }
    } catch (error) {
        console.error('Streaming error:', error);
        throw error;
    }
};