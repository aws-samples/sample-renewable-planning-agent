import {
  Tabs,
  Modal,
  Box,
  SpaceBetween,
  Button,
} from "@cloudscape-design/components";
import { useEffect, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";

const SECTION_COLORS = {
  reasoning: { bg: "rgba(0, 102, 204, 0.1)", border: "rgba(0, 102, 204, 0.2)", text: "#0066cc" },
  toolUse: { bg: "rgba(245, 158, 11, 0.1)", border: "rgba(245, 158, 11, 0.2)", text: "#d97706" },
  response: { bg: "rgba(99, 102, 241, 0.1)", border: "rgba(99, 102, 241, 0.2)", text: "#6366f1" }
};

// Agent Response Component
const AgentResponse = ({ 
  message, 
  isWorking, 
  isThinking, 
  showSections = true
}: {
  message: any;
  isStreaming: boolean;
  isWorking: boolean;
  isThinking: boolean;
  currentToolEvents: any[];
  currentReasoning: string;
  showSections?: boolean;
}) => {
  
  // Parse message text to identify sections
  const parseMessageSections = (text: string) => {
    if (!text) return [];
    
    const sections = [];
    const lines = text.split('\n');
    let currentSection = { type: 'response', content: '' };
    
    for (const line of lines) {
      if (line.startsWith('💬 Response:')) {
        if (currentSection.content.trim()) sections.push(currentSection);
        currentSection = { type: 'response', content: '' };
      } else if (line.startsWith('🧠 Reasoning:')) {
        if (currentSection.content.trim()) sections.push(currentSection);
        currentSection = { type: 'reasoning', content: '' };
      } else if (line.includes('🔧 ToolUse:')) {
        if (currentSection.content.trim()) sections.push(currentSection);
        // Extract tool name and format content
        const toolMatch = line.match(/🔧 ToolUse: (\w+) -> Input: (.*)/);
        if (toolMatch) {
          const [, toolName, input] = toolMatch;
          currentSection = { type: 'toolUse', content: `**${toolName}**\n\n\`${input}\`` };
        } else {
          currentSection = { type: 'toolUse', content: line };
        }
      } else {
        currentSection.content += (currentSection.content ? '\n' : '') + line;
      }
    }
    
    if (currentSection.content.trim()) sections.push(currentSection);
    return sections;
  };
  
  const sections = parseMessageSections(message.text);
  
  return (
    <div style={{ fontSize: "14px" }} className="markdown-content">
      {showSections ? (
        /* Sectioned View */
        sections.map((section, idx) => {
          const sectionTheme = SECTION_COLORS[section.type as keyof typeof SECTION_COLORS] || SECTION_COLORS.response;
          return (
            <div key={idx} style={{
              margin: "8px 0",
              padding: "12px",
              background: sectionTheme.bg,
              border: `1px solid ${sectionTheme.border}`,
              borderRadius: "8px",
              borderLeft: `4px solid ${sectionTheme.text}`
            }}>
              <div style={{
                fontSize: "11px",
                fontWeight: "600",
                color: sectionTheme.text,
                marginBottom: "6px",
                textTransform: "uppercase",
                letterSpacing: "0.5px"
              }}>
                {section.type === 'reasoning' && '🧠 Reasoning'}
                {section.type === 'toolUse' && '🔧 Tool Usage'}
                {section.type === 'response' && '💬 Response'}
              </div>
              <ReactMarkdown
                components={{
                  h1: ({ node, ...props }) => <h1 style={{ fontSize: "16px", fontWeight: "600", margin: "8px 0 6px" }} {...props} />,
                  h2: ({ node, ...props }) => <h2 style={{ fontSize: "15px", fontWeight: "600", margin: "6px 0 4px" }} {...props} />,
                  h3: ({ node, ...props }) => <h3 style={{ fontSize: "14px", fontWeight: "600", margin: "4px 0 2px" }} {...props} />,
                  p: ({ node, ...props }) => <p style={{ margin: "4px 0", lineHeight: "1.4" }} {...props} />,
                  ul: ({ node, ...props }) => <ul style={{ margin: "4px 0", paddingLeft: "16px" }} {...props} />,
                  ol: ({ node, ...props }) => <ol style={{ margin: "4px 0", paddingLeft: "16px" }} {...props} />,
                  li: ({ node, ...props }) => <li style={{ margin: "2px 0" }} {...props} />,
                  code: ({ node, ...props }) => <code style={{ background: "rgba(0,0,0,0.1)", padding: "8px 12px", borderRadius: "6px", fontSize: "12px", fontFamily: "monospace", display: "block", margin: "8px 0", whiteSpace: "pre-wrap" }} {...props} />
                }}
              >
                {section.content}
              </ReactMarkdown>
            </div>
          );
        })
      ) : (
        /* Plain View */
        <ReactMarkdown
          components={{
            h1: ({ node, ...props }) => <h1 style={{ fontSize: "18px", fontWeight: "600", margin: "12px 0 8px" }} {...props} />,
            h2: ({ node, ...props }) => <h2 style={{ fontSize: "16px", fontWeight: "600", margin: "10px 0 6px" }} {...props} />,
            h3: ({ node, ...props }) => <h3 style={{ fontSize: "15px", fontWeight: "600", margin: "8px 0 4px" }} {...props} />,
            p: ({ node, ...props }) => <p style={{ margin: "8px 0", lineHeight: "1.5" }} {...props} />,
            ul: ({ node, ...props }) => <ul style={{ margin: "8px 0", paddingLeft: "20px" }} {...props} />,
            ol: ({ node, ...props }) => <ol style={{ margin: "8px 0", paddingLeft: "20px" }} {...props} />,
            li: ({ node, ...props }) => <li style={{ margin: "4px 0" }} {...props} />,
            code: ({ node, ...props }) => <code style={{ background: "rgba(0,0,0,0.1)", padding: "8px 12px", borderRadius: "6px", fontSize: "12px", fontFamily: "monospace", display: "block", margin: "8px 0", whiteSpace: "pre-wrap" }} {...props} />
          }}
        >
          {message.text}
        </ReactMarkdown>
      )}
      
      {/* Status Indicators */}
      {isWorking && (
        <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#666", marginTop: "8px" }}>
          <span style={{
            display: "inline-block", width: "8px", height: "8px", backgroundColor: "#ffc107",
            borderRadius: "50%", animation: "pulse 1.5s ease-in-out infinite"
          }} />
          <span style={{ fontSize: "13px", fontStyle: "italic" }}>Working...</span>
        </div>
      )}
      
      {isThinking && !message.text && (
        <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#666" }}>
          <span style={{
            display: "inline-block", width: "8px", height: "8px", backgroundColor: "#0066cc",
            borderRadius: "50%", animation: "pulse 1.5s ease-in-out infinite"
          }} />
          <span style={{ fontSize: "13px", fontStyle: "italic" }}>Thinking...</span>
        </div>
      )}
      
      {/* Streaming Indicator */}
      {message.streaming && message.text && !isWorking && (
        <span style={{
          display: "inline-block", width: "8px", height: "8px", backgroundColor: "#0066cc",
          borderRadius: "50%", marginLeft: "6px", animation: "pulse 1.5s ease-in-out infinite"
        }} />
      )}
    </div>
  );
};


import Layout from "../../common/components/Layout";
import { AssetPollingService, streamChatMessage } from "./polling-api";
import Map from "./Map";
import "../../liquidglass.css";

const SHOW_MAP_NOTIFICATIONS = true;

const Chat = () => {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<
    Array<{ 
      text: string; 
      sender: "user" | "ai"; 
      streaming?: boolean;
      subagent?: boolean;
      subagent_name?: string;
      toolEvents?: Array<{
        type: string;
        content: string;
        tool_name?: string;
        accumulated?: boolean;
      }>;
      reasoning?: string;
    }>
  >([]);
  const [isWaiting, setIsWaiting] = useState(false);
  const [showLocationModal, setShowLocationModal] = useState(false);
  const [selectedLocation, setSelectedLocation] = useState<{
    lat: number;
    lon: number;
  } | null>(null);
  const [currentReasoning, setCurrentReasoning] = useState<string>("");
  const [currentToolEvents, setCurrentToolEvents] = useState<
    Array<{
      type: string;
      content: string;
      tool_name?: string;
      accumulated?: boolean;
    }>
  >([]);
  const [currentProjectId, setCurrentProjectId] = useState<string>(
    () => {
      const stored = localStorage.getItem("projectId") || "";
      console.log('Initial project ID from localStorage:', stored);
      return stored;
    }
  );
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [projectAssets, setProjectAssets] = useState<any>(null);
  const [selectedAsset, setSelectedAsset] = useState<any>(null);
  const [showAssetModal, setShowAssetModal] = useState(false);
  const [geojsonLayers, setGeojsonLayers] = useState<any[]>([]);
  const [collapsedAssets, setCollapsedAssets] = useState<Set<string>>(
    new Set()
  );
  const [showQuickActions, setShowQuickActions] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const screenWidth = window.innerWidth;
    if (screenWidth < 768) return Math.min(screenWidth * 0.9, 300);
    if (screenWidth < 1024) return 350;
    return 400;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [showResizeHandle, setShowResizeHandle] = useState(false);
  const [selectedCenterpoint, setSelectedCenterpoint] = useState<{
    lat: number;
    lon: number;
  } | null>(null);
  const [assetNotifications, setAssetNotifications] = useState<
    Array<{ agent: string; filename: string; timestamp: number }>
  >([]);
  const [showAssetNotifications, setShowAssetNotifications] = useState(() => {
    const saved = localStorage.getItem("showAssetNotifications");
    return saved !== null ? saved === "true" : true;
  });
  const [, setPreviousAssetPaths] = useState<Set<string>>(
    new Set()
  );
  const [activeTab, setActiveTab] = useState("chat");
  const [highlightedAsset, setHighlightedAsset] = useState<string | null>(null);
  const [showStatusPrompt, setShowStatusPrompt] = useState(false);
  const [statusPromptDismissed, setStatusPromptDismissed] = useState(false);
  const [showSections, setShowSections] = useState(() => 
    localStorage.getItem('showChatSections') !== 'false'
  );
  const [subagentWindows, setSubagentWindows] = useState<Record<string, {messages: string; minimized: boolean}>>({});
  const [lastSubagentState, setLastSubagentState] = useState(false);
  const [pollingConnected, setPollingConnected] = useState(false);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingServiceRef = useRef<AssetPollingService | null>(null);

  // Apply glass effect to modal when it opens
  useEffect(() => {
    if (showAssetModal) {
      setTimeout(() => {
        const modalContent = document.querySelector(
          '[class*="awsui_content"]'
        ) as HTMLElement;
        if (modalContent) {
          modalContent.style.background = "rgba(255, 255, 255, 0.4)";
          modalContent.style.backdropFilter = "blur(20px)";
          (modalContent.style as any).webkitBackdropFilter = "blur(20px)";
        }
      }, 0);
    }
  }, [showAssetModal]);

  // Handle sidebar resize and window resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isResizing) {
        const maxWidth = window.innerWidth * 0.6;
        const minWidth = window.innerWidth < 768 ? 250 : 300;
        const newWidth = Math.max(minWidth, Math.min(e.clientX, maxWidth));
        setSidebarWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      setShowResizeHandle(false);
    };

    const handleWindowResize = () => {
      if (!isResizing) {
        const screenWidth = window.innerWidth;
        const maxAllowed = screenWidth * 0.6;
        if (sidebarWidth > maxAllowed) {
          if (screenWidth < 768)
            setSidebarWidth(Math.min(screenWidth * 0.9, 300));
          else if (screenWidth < 1024) setSidebarWidth(350);
          else setSidebarWidth(400);
        }
      }
    };

    if (isResizing) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    }

    window.addEventListener("resize", handleWindowResize);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      window.removeEventListener("resize", handleWindowResize);
    };
  }, [isResizing, sidebarWidth]);

  const scrollToBottom = () => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  };

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const isScrollable = scrollHeight > clientHeight;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      setShowScrollButton(isScrollable && !isNearBottom && messages.length > 0);
    };

    container.addEventListener("scroll", handleScroll);
    const resizeObserver = new ResizeObserver(handleScroll);
    resizeObserver.observe(container);

    return () => {
      container.removeEventListener("scroll", handleScroll);
      resizeObserver.disconnect();
    };
  }, [messages]);

  useEffect(() => {
    // Listen for project changes from TopBar
    const handleProjectChange = () => {
      const newProjectId = localStorage.getItem("projectId") || "";
        // Clear everything immediately
      setMessages([]);
      setCurrentReasoning("");
      setCurrentToolEvents([]);
      setProjectAssets(null);
      setGeojsonLayers([]); // Clear map layers immediately
      setPreviousAssetPaths(new Set());
      setShowStatusPrompt(false);
      setStatusPromptDismissed(false);
      
      // Update project ID last to trigger effects
      setCurrentProjectId(newProjectId);
      

    };

    window.addEventListener("storage", handleProjectChange);
    return () => window.removeEventListener("storage", handleProjectChange);
  }, [currentProjectId]);

  // Load initial assets when component mounts or project changes
  useEffect(() => {

    
    if (currentProjectId && pollingServiceRef.current) {

      pollingServiceRef.current.startPolling(
        currentProjectId,
        handleAssetsUpdate,
        15000 // Poll every 15 seconds
      );
    } else if (!currentProjectId) {
      // Clear everything if no project selected

      if (pollingServiceRef.current) {
        pollingServiceRef.current.stopPolling();
      }
      setProjectAssets(null);
      setGeojsonLayers([]);
    }
  }, [currentProjectId, pollingConnected]);
  
  // Separate effect to handle immediate project ID changes
  useEffect(() => {

    // Force clear map when project changes
    if (!currentProjectId) {
      setGeojsonLayers([]);
      setProjectAssets(null);
    }
  }, [currentProjectId]);

  // Initialize polling service for assets updates
  useEffect(() => {
    const initPollingService = () => {
      if (pollingServiceRef.current) {
        pollingServiceRef.current.stopPolling();
      }

      const pollingService = new AssetPollingService();
      pollingServiceRef.current = pollingService;
      
      setPollingConnected(true);
      setPollingError(null);
      

    };

    initPollingService();

    return () => {
      if (pollingServiceRef.current) {
        pollingServiceRef.current.stopPolling();
      }
    };
  }, []);

  // Handle assets update from WebSocket
  const handleAssetsUpdate = async (assets: any, newAssetKeys?: string[]) => {
    // Get the current project ID to ensure we're updating the right project
    const latestProjectId = localStorage.getItem('projectId') || currentProjectId;
    
    if (!latestProjectId) {
      setProjectAssets(null);
      setGeojsonLayers([]);
      return;
    }
    
    // Validate that this asset update is for the current project
    if (assets.project_id && assets.project_id !== latestProjectId) {
      return;
    }
    
    // Show notifications for new assets if provided
    if (newAssetKeys && newAssetKeys.length > 0 && showAssetNotifications) {
      newAssetKeys.forEach((key: string) => {
        const parts = key.split('/');
        const agent = parts[1] || "unknown";
        const filename = parts[parts.length - 1] || key;
        setAssetNotifications((prev) => [
          ...prev,
          { agent, filename, timestamp: Date.now() },
        ]);
      });
    }

    // Update previous paths for fallback detection
    if (assets.assets) {
      setPreviousAssetPaths(new Set(assets.assets.map((a: any) => a.path)));
    }

    setProjectAssets(assets);

    // Collapse all asset groups by default
    if (assets.assets) {
      const agents = [
        ...new Set(
          assets.assets.map((a: any) => a.path.split("/")[0] || "other")
        ),
      ] as string[];
      setCollapsedAssets(new Set(agents));
    }

    // Load GeoJSON layers only if we have assets and they belong to current project
    if (assets.geojson_files && assets.geojson_files.length > 0 && latestProjectId) {
      const API_URL = import.meta.env.VITE_API_URL || window.location.origin;
      const cleanUrl = API_URL.endsWith("/") ? API_URL.slice(0, -1) : API_URL;
      
      const layers = await Promise.all(
        assets.geojson_files.map(async (filename: string) => {
          try {
            const assetUrl = `${cleanUrl}/projects/${latestProjectId}/${filename}`;
            const geojsonResponse = await fetch(assetUrl);

            if (!geojsonResponse.ok) {
              console.error('Failed to load GeoJSON:', filename, 'Status:', geojsonResponse.status);
              return null;
            }

            const geojson = await geojsonResponse.json();
            return { filename, geojson };
          } catch (error) {
            console.error("Error loading GeoJSON:", filename, error);
            return null;
          }
        })
      );
      const validLayers = layers.filter((l: any) => l !== null);
      setGeojsonLayers(validLayers);
    } else {
      // No GeoJSON files or no project, clear the map
      setGeojsonLayers([]);
    }

    // Show status prompt only if project has assets, no messages, and hasn't been dismissed
    if (assets.total_count > 0 && messages.length === 0 && !statusPromptDismissed) {
      // Double check messages length in case of stale closure
      setMessages(currentMessages => {
        if (currentMessages.length === 0) {
          setShowStatusPrompt(true);
        }
        return currentMessages;
      });
    }
  };



  // Auto-dismiss notifications after 5 seconds
  useEffect(() => {
    if (assetNotifications.length > 0) {
      const timer = setTimeout(() => {
        setAssetNotifications((prev) => prev.slice(1));
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [assetNotifications]);

  // Listen for notification preference changes
  useEffect(() => {
    const handleStorageChange = () => {
      const saved = localStorage.getItem("showAssetNotifications");
      setShowAssetNotifications(saved !== "false");
    };
    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  const submitMessageForm = async () => {
    if (!message.trim()) return;

    if (!currentProjectId) {
      alert("Please create or select a project before sending messages.");
      return;
    }

    const userMessage = message;
    const isFirstMessage = messages.length === 0;

    setMessages([...messages, { text: userMessage, sender: "user" }]);
    setMessage("");
    setIsWaiting(true);

    setCurrentReasoning("");
    setCurrentToolEvents([]);

    const aiMessageIndex = messages.length + 1;
    setMessages((prev) => [
      ...prev,
      { text: "", sender: "ai", streaming: true },
    ]);

    // Use HTTP streaming for chat
    await streamChatMessage(
      userMessage,
      (chunk, subagent, subagentName) => {
        setIsWaiting(false);
        setIsThinking(false);
        setIsWorking(false);
        
        // Check if subagent state changed (finished)
        if (lastSubagentState && !subagent) {
          // Subagent just finished, trigger asset update with latest project ID
          const latestProjectId = localStorage.getItem('projectId') || currentProjectId;
          if (latestProjectId && pollingServiceRef.current) {
            pollingServiceRef.current.requestAssets(latestProjectId);
          }
        }
        setLastSubagentState(subagent || false);
        
        if (subagent && subagentName) {
          // Update subagent window
          setSubagentWindows(prev => ({
            ...prev,
            [subagentName]: {
              messages: (prev[subagentName]?.messages || '') + chunk,
              minimized: prev[subagentName]?.minimized || false
            }
          }));
        } else {
          // Add to main messages
          setMessages((prev) => {
            const updated = [...prev];
            updated[aiMessageIndex] = {
              ...updated[aiMessageIndex],
              text: updated[aiMessageIndex].text + chunk,
              streaming: true,
            };
            return updated;
          });
          
          // Check if the agent response contains a project ID and update it
          const projectIdMatch = chunk.match(/project[_\s-]?id[:\s]+([a-f0-9-]{36})/i);
          if (projectIdMatch && projectIdMatch[1] !== currentProjectId) {
            const newProjectId = projectIdMatch[1];
            console.log('Agent provided new project ID:', newProjectId);
            localStorage.setItem('projectId', newProjectId);
            setCurrentProjectId(newProjectId);
            window.dispatchEvent(new Event('storage'));
          }
        }
      },
      undefined, // onReasoning - simplified for now
      currentProjectId,
      isFirstMessage
    );

    // Mark streaming as complete
    setMessages((prev) => {
      const updated = [...prev];
      updated[aiMessageIndex] = {
        ...updated[aiMessageIndex],
        streaming: false,
      };
      return updated;
    });

    setIsWaiting(false);
    setIsThinking(false);
    setIsWorking(false);
  };

  return (
    <>
      <Layout
        content={
          <div
            style={{
              display: "flex",
              height: "calc(100vh - 60px)",
              width: "100%",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${sidebarWidth}px`,
                minWidth: window.innerWidth < 768 ? "250px" : "300px",
                maxWidth: "60vw",
                backgroundColor: "#ffffff",
                display: "flex",
                flexDirection: "column",
                borderRight: "1px solid #e5e5e5",
                position: "relative",
              }}
            >
              <Tabs
                variant="container"
                tabs={[
                  {
                    label: `Map${
                      SHOW_MAP_NOTIFICATIONS && geojsonLayers.length > 0
                        ? " •"
                        : ""
                    }`,
                    id: "map",
                    content: (
                      <div
                        style={{
                          padding: "24px",
                          height: "calc(100vh - 150px)",
                          display: "flex",
                          flexDirection: "column",
                          gap: "12px",
                        }}
                      >
                        {geojsonLayers.length === 0 && (
                          <div
                            className="glass-message-warning glass-refract"
                            style={{
                              padding: "12px 16px",
                              borderRadius: "12px",
                              fontSize: "13px",
                              color: "#856404",
                            }}
                          >
                            ⚠️ Map will update with site boundaries once the
                            agent creates them
                          </div>
                        )}
                        <div
                          style={{
                            flex: 1,
                            borderRadius: "8px",
                            overflow: "hidden",
                            border: "1px solid #d0d0d0",
                            background: "#e8f4f8",
                            position: "relative",
                          }}
                        >
                          <Map
                            geojsonLayers={geojsonLayers}
                            selectedCenterpoint={selectedCenterpoint}
                            onLocationClick={(lat, lon) => {
                              setSelectedLocation({ lat, lon });
                              setSelectedCenterpoint({ lat, lon });
                              setShowLocationModal(true);
                            }}
                          />
                        </div>
                      </div>
                    ),
                  },
                  {
                    label: `Assets${
                      showAssetNotifications && projectAssets?.total_count
                        ? ` (${projectAssets.total_count})`
                        : ""
                    }`,
                    id: "assets",
                    content: (
                      <div
                        style={{
                          padding: "24px",
                          height: "calc(100vh - 150px)",
                          overflowY: "auto",
                          // background: "#fafafa",
                        }}
                      >
                        {!projectAssets || projectAssets.total_count === 0 ? (
                          <div
                            style={{
                              // height: "100%",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                            }}
                          >
                            <p
                              style={{
                                margin: 0,
                                color: "#999",
                                fontSize: "14px",
                              }}
                            >
                              Project assets will appear here as they are
                              generated
                            </p>
                          </div>
                        ) : (
                          <div
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              gap: "16px",
                            }}
                          >
                            {projectAssets?.assets &&
                              Object.entries(
                                projectAssets.assets.reduce(
                                  (acc: any, asset: any) => {
                                    const agent =
                                      asset.path.split("/")[0] || "other";
                                    if (!acc[agent]) acc[agent] = [];
                                    acc[agent].push(asset);
                                    return acc;
                                  },
                                  {}
                                )
                              ).map(([agent, assets]: [string, any]) => (
                                <div
                                  key={agent}
                                  className="glass-message glass-refract"
                                  style={{
                                    borderRadius: "16px",
                                    overflow: "hidden",
                                  }}
                                >
                                  <div
                                    onClick={() =>
                                      setCollapsedAssets((prev) => {
                                        const next = new Set(prev);
                                        if (next.has(agent)) next.delete(agent);
                                        else next.add(agent);
                                        return next;
                                      })
                                    }
                                    style={{
                                      padding: "14px 18px",
                                      cursor: "pointer",
                                      display: "flex",
                                      alignItems: "center",
                                      gap: "10px",
                                      transition: "background 0.2s",
                                    }}
                                    onMouseEnter={(e) =>
                                      (e.currentTarget.style.background =
                                        "rgba(0, 0, 0, 0.02)")
                                    }
                                    onMouseLeave={(e) =>
                                      (e.currentTarget.style.background =
                                        "transparent")
                                    }
                                  >
                                    <span
                                      style={{
                                        fontSize: "12px",
                                        color: "#666",
                                      }}
                                    >
                                      {collapsedAssets.has(agent) ? "▶" : "▼"}
                                    </span>
                                    <span
                                      style={{
                                        fontWeight: "600",
                                        fontSize: "14px",
                                        color: "#2c2c2c",
                                      }}
                                    >
                                      {agent}
                                    </span>
                                    <span
                                      style={{
                                        color: "#666",
                                        fontSize: "11px",
                                        background: "rgba(0, 0, 0, 0.05)",
                                        padding: "2px 8px",
                                        borderRadius: "12px",
                                      }}
                                    >
                                      {assets.length}
                                    </span>
                                  </div>
                                  {!collapsedAssets.has(agent) && (
                                    <div
                                      style={{ padding: "0 12px 12px 12px" }}
                                    >
                                      {assets.map((asset: any, idx: number) => (
                                        <div
                                          key={asset.path}
                                          onClick={async () => {
                                            try {
                                              const API_URL =
                                                import.meta.env.VITE_API_URL ||
                                                window.location.origin;
                                              const cleanUrl = API_URL.endsWith(
                                                "/"
                                              )
                                                ? API_URL.slice(0, -1)
                                                : API_URL;
                                              const assetUrl = `${cleanUrl}/projects/${currentProjectId}/${asset.path}`;

                                              setSelectedAsset({
                                                ...asset,
                                                url: assetUrl,
                                              });
                                              setShowAssetModal(true);
                                            } catch (error) {
                                              console.error(
                                                "Error loading asset:",
                                                error
                                              );
                                            }
                                          }}
                                          style={{
                                            padding: "10px 14px",
                                            cursor: "pointer",
                                            borderRadius: "8px",
                                            transition: "background 0.2s",
                                            background:
                                              highlightedAsset === asset.path
                                                ? "rgba(46, 184, 92, 0.2)"
                                                : "rgba(255, 255, 255, 0.4)",
                                            marginTop: idx > 0 ? "6px" : "0",
                                          }}
                                          onMouseEnter={(e) =>
                                            (e.currentTarget.style.background =
                                              "rgba(255, 255, 255, 0.7)")
                                          }
                                          onMouseLeave={(e) =>
                                            (e.currentTarget.style.background =
                                              "rgba(255, 255, 255, 0.4)")
                                          }
                                        >
                                          <div
                                            style={{
                                              fontSize: "13px",
                                              fontWeight: "500",
                                              color: "#2c2c2c",
                                            }}
                                          >
                                            {asset.path.split("/").pop()}
                                          </div>
                                          <div
                                            style={{
                                              fontSize: "11px",
                                              color: "#888",
                                              marginTop: "3px",
                                            }}
                                          >
                                            {(asset.size / 1024).toFixed(1)} KB
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                          </div>
                        )}
                      </div>
                    ),
                  },
                ]}
              />
            </div>
            <div
              onMouseDown={() => setIsResizing(true)}
              onMouseEnter={() => setShowResizeHandle(true)}
              onMouseLeave={() => !isResizing && setShowResizeHandle(false)}
              style={{
                width: "12px",
                cursor: "col-resize",
                background: "transparent",
                position: "relative",
                zIndex: 10,
                marginLeft: "-6px",
                marginRight: "-6px",
              }}
            >
              {(showResizeHandle || isResizing) && (
                <div
                  style={{
                    position: "absolute",
                    left: "50%",
                    top: "50%",
                    transform: "translate(-50%, -50%)",
                    width: "3px",
                    height: "60px",
                    borderRadius: "3px",
                    background:
                      "linear-gradient(180deg, rgba(0, 102, 204, 0) 0%, rgba(0, 102, 204, 0.4) 50%, rgba(0, 102, 204, 0) 100%)",
                    transition: "opacity 0.2s",
                    opacity: isResizing ? 1 : 0.6,
                  }}
                />
              )}
            </div>
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                background: "#ffffff",
                overflow: "hidden",
                position: "relative",
              }}
            >
              {Object.entries(subagentWindows).map(([agentName, window], index) => (
                <div
                  key={agentName}
                  style={{
                    position: "absolute",
                    bottom: "20px",
                    right: `${20 + (index * 470)}px`,
                    width: "450px",
                    height: window.minimized ? "50px" : "400px",
                    background: "rgba(255, 255, 255, 0.95)",
                    backdropFilter: "blur(20px)",
                    borderRadius: "16px",
                    boxShadow: "0 20px 40px rgba(0,0,0,0.15)",
                    border: "1px solid rgba(255, 255, 255, 0.6)",
                    zIndex: 999,
                    display: "flex",
                    flexDirection: "column",
                    transition: "height 0.3s ease",
                  }}
                >
                  <div
                    style={{
                      padding: "12px 16px",
                      borderBottom: window.minimized ? "none" : "1px solid rgba(0,0,0,0.1)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      cursor: "pointer",
                    }}
                    onClick={() => setSubagentWindows(prev => ({
                      ...prev,
                      [agentName]: { ...prev[agentName], minimized: !prev[agentName].minimized }
                    }))}
                  >
                    <span style={{ fontSize: "14px", fontWeight: "600", color: "#16a34a" }}>
                      🤖 {agentName.toUpperCase()}
                    </span>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSubagentWindows(prev => ({
                            ...prev,
                            [agentName]: { ...prev[agentName], minimized: !prev[agentName].minimized }
                          }));
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          fontSize: "14px",
                          cursor: "pointer",
                          color: "#666",
                        }}
                      >
                        {window.minimized ? "□" : "_"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSubagentWindows(prev => {
                            const newWindows = { ...prev };
                            delete newWindows[agentName];
                            return newWindows;
                          });
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          fontSize: "16px",
                          cursor: "pointer",
                          color: "#666",
                        }}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  {!window.minimized && (
                    <div
                      style={{
                        flex: 1,
                        overflowY: "auto",
                        padding: "16px",
                        fontSize: "16px",
                        lineHeight: "1.6",
                      }}
                    >
                      <ReactMarkdown
                        components={{
                          h1: ({ node, ...props }) => <h1 style={{ fontSize: "20px", fontWeight: "600", margin: "16px 0 12px", color: "#2c2c2c" }} {...props} />,
                          h2: ({ node, ...props }) => <h2 style={{ fontSize: "18px", fontWeight: "600", margin: "14px 0 10px", color: "#2c2c2c" }} {...props} />,
                          h3: ({ node, ...props }) => <h3 style={{ fontSize: "16px", fontWeight: "600", margin: "12px 0 8px", color: "#2c2c2c" }} {...props} />,
                          p: ({ node, ...props }) => <p style={{ margin: "12px 0", lineHeight: "1.6", color: "#2c2c2c" }} {...props} />,
                          ul: ({ node, ...props }) => <ul style={{ margin: "12px 0", paddingLeft: "24px", color: "#2c2c2c" }} {...props} />,
                          ol: ({ node, ...props }) => <ol style={{ margin: "12px 0", paddingLeft: "24px", color: "#2c2c2c" }} {...props} />,
                          li: ({ node, ...props }) => <li style={{ margin: "6px 0", lineHeight: "1.5" }} {...props} />,
                          code: ({ node, ...props }) => <code style={{ background: "rgba(0,0,0,0.1)", padding: "12px 16px", borderRadius: "8px", fontSize: "14px", fontFamily: "monospace", display: "block", margin: "12px 0", whiteSpace: "pre-wrap", color: "#2c2c2c" }} {...props} />,
                          strong: ({ node, ...props }) => <strong style={{ fontWeight: "600", color: "#16a34a" }} {...props} />,
                          em: ({ node, ...props }) => <em style={{ fontStyle: "italic", color: "#666" }} {...props} />
                        }}
                      >
                        {window.messages}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              ))}
              {assetNotifications.length > 0 && (
                <div
                  style={{
                    position: "absolute",
                    top: "16px",
                    right: "16px",
                    zIndex: 1000,
                    maxWidth: "250px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px",
                  }}
                >
                  {assetNotifications.slice(-3).map((notif) => (
                    <div
                      key={`${notif.timestamp}-${notif.filename}`}
                      className="glass-message-tool glass-refract"
                      style={{
                        padding: "8px 12px",
                        borderRadius: "8px",
                        fontSize: "12px",
                        animation: "fadeIn 0.3s ease-out",
                        cursor: "pointer",
                      }}
                      onClick={() => {
                        setActiveTab("assets");
                        setHighlightedAsset(`${notif.agent}/${notif.filename}`);
                        setAssetNotifications((prev) =>
                          prev.filter((n) => n.timestamp !== notif.timestamp)
                        );
                        setTimeout(() => setHighlightedAsset(null), 3000);
                      }}
                    >
                      <div
                        style={{
                          fontWeight: "600",
                          color: "#16a34a",
                          fontSize: "11px",
                          marginBottom: "2px",
                        }}
                      >
                        📄 New Asset
                      </div>
                      <div style={{ fontSize: "11px", color: "#2c2c2c" }}>
                        <strong>{notif.agent}</strong>: {notif.filename}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <Tabs
                variant="container"
                activeTabId={activeTab}
                onChange={({ detail }) => setActiveTab(detail.activeTabId)}
                tabs={[
                  {
                    label: "Chat",
                    id: "chat",
                    content: (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          padding: "24px",
                          height: "calc(100vh - 150px)",
                        }}
                      >
                        <div
                          ref={messagesContainerRef}
                          style={{
                            flex: 1,
                            overflowY: "auto",
                            padding: "24px",
                            background: "#fafafa",
                            borderRadius: "6px",
                            position: "relative",
                            maxHeight: "calc(100vh - 200px)",
                          }}
                        >
                          <div
                            style={{
                              position: "fixed",
                              top: "110px",
                              right: "16px",
                              zIndex: 1000,
                              borderRadius: "16px",
                              background: "rgba(255, 255, 255, 0.95)",
                              backdropFilter: "blur(20px)",
                              boxShadow: "0 20px 40px rgba(0,0,0,0.15), 0 8px 16px rgba(0,0,0,0.1), inset 0 1px 0 rgba(255,255,255,0.8)",
                              border: "1px solid rgba(255, 255, 255, 0.6)",
                              minWidth: "220px",
                              maxWidth: "300px",
                              maxHeight: "80vh",
                              overflowY: "auto",
                            }}
                          >
                            <div
                              onClick={() => {
                                setShowQuickActions(!showQuickActions);
                              }}
                              style={{
                                padding: "12px 16px",
                                fontSize: "13px",
                                fontWeight: "600",
                                color: "#0066cc",
                                cursor: "pointer",
                                userSelect: "none",
                                display: "flex",
                                alignItems: "center",
                                gap: "8px",
                                borderRadius: "12px",
                                transition: "background 0.2s",
                              }}
                              onMouseEnter={(e) =>
                                (e.currentTarget.style.background =
                                  "rgba(245, 245, 245, 0.5)")
                              }
                              onMouseLeave={(e) =>
                                (e.currentTarget.style.background =
                                  "transparent")
                              }
                            >
                              <span style={{ fontSize: "10px" }}>
                                {showQuickActions ? "▼" : "▶"}
                              </span>
                              ⚡ Sample Prompts
                            </div>
                            {showQuickActions && (
                              <div
                                style={{
                                  borderTop:
                                    "1px solid rgba(229, 229, 229, 0.5)",
                                }}
                              >
                                {[
                                  {
                                    title: "🤖 Agent Help",
                                    prompt: "How can you help me with wind farm development?"
                                  },
                                  {
                                    title: "🛠️ Available Tools",
                                    prompt: "What tools do you have access to?"
                                  },
                                  {
                                    title: "🗺️ Site Analysis",
                                    prompt: `Analyze the terrain and identify unbuildable areas at coordinates 35.067482, -101.395466 for project id ${currentProjectId}. \nUse the turbine model IEA_Reference_3.4MW_130 to calculate proportional setback distances specified in the constraints but use a setback distance of 200 meters from waterbodies.`
                                  },
                                  {
                                    title: "📐 Grid Layout",
                                    prompt: `Create an offset grid wind farm layout at coordinates 35.067482, -101.395466. \nMake sure that none of the turbines are in unbuildable areas. If any turbines are in restricted zones, relocate those turbines but maintain the offset grid pattern. Use 9 turbines with IEA_Reference_3.4MW_130 model. \nThe layout needs to be offset grid specifically.`
                                  },
                                  {
                                    title: "🏗️ Complete Development",
                                    prompt: `Create a complete wind farm development plan for coordinates 35.067482, -101.395466 for project id ${currentProjectId}. \nTarget capacity: 30MW. Use turbine model IEA_Reference_3.4MW_130.`
                                  },
                                  {
                                    title: "🌀 Spiral Layout",
                                    prompt: `Design a spiral wind farm layout at 35.067482, -101.395466 for project id ${currentProjectId}. \nRequirements: \n- 20 turbines using IEA_Reference_3.4MW_130 \n- Minimum 9D spacing between turbines (9 times rotor diameter) \n- Avoid any water bodies or roads \n- Optimize for prevailing wind direction from the southwest \n- Only create the layout`
                                  },
                                  {
                                    title: "⚡ Performance Tips",
                                    prompt: "What are the best practices for optimizing wind farm layouts to minimize wake losses while maximizing energy production? Consider turbine spacing, orientation, and terrain factors."
                                  },
                                  {
                                    title: "📊 Location Compare",
                                    prompt: "Compare the wind resource potential between these two locations: Location A: 35.067482, -101.395466 (Amarillo, TX) Location B: 39.8283, -98.5795 (Kansas). Provide wind resource analysis for both locations and recommend which would be better for a 50MW wind farm."
                                  },
                                  {
                                    title: "📍 Analyze Location",
                                    action: () => {
                                      setSelectedLocation({
                                        lat: 35.067482,
                                        lon: -101.395466,
                                      });
                                      setShowLocationModal(true);
                                    }
                                  }
                                ].map((action, index) => (
                                  <button
                                    key={index}
                                    onClick={() => {
                                      if (action.action) {
                                        action.action();
                                      } else if (action.prompt) {
                                        setMessage(action.prompt);
                                        setShowQuickActions(false);
                                      }
                                    }}
                                    style={{
                                      width: "100%",
                                      padding: "10px 16px",
                                      background: "rgba(255, 255, 255, 0.6)",
                                      color: "#2c2c2c",
                                      border: "none",
                                      borderBottom: index < 8 ? "1px solid rgba(229, 229, 229, 0.5)" : "none",
                                      fontSize: "12px",
                                      cursor: "pointer",
                                      textAlign: "left",
                                      transition: "background 0.2s",
                                      backdropFilter: "blur(10px)",
                                    }}
                                    onMouseEnter={(e) =>
                                      (e.currentTarget.style.background =
                                        "rgba(245, 245, 245, 0.8)")
                                    }
                                    onMouseLeave={(e) =>
                                      (e.currentTarget.style.background =
                                        "rgba(255, 255, 255, 0.6)")
                                    }
                                  >
                                    {action.title}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                          {showStatusPrompt && (
                            <div
                              className="glass-message-warning glass-refract"
                              style={{
                                padding: "16px 20px",
                                borderRadius: "12px",
                                marginTop: "20px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                gap: "12px",
                              }}
                            >
                              <div style={{ flex: 1 }}>
                                <div
                                  style={{
                                    fontWeight: "600",
                                    marginBottom: "4px",
                                    color: "#856404",
                                  }}
                                >
                                  Welcome back!
                                </div>
                                <div
                                  style={{ fontSize: "13px", color: "#856404" }}
                                >
                                  Would you like to check the current status of
                                  this project?
                                </div>
                              </div>
                              <div style={{ display: "flex", gap: "8px" }}>
                                <button
                                  onClick={() => {
                                    setShowStatusPrompt(false);
                                    setStatusPromptDismissed(true);
                                  }}
                                  style={{
                                    padding: "6px 12px",
                                    fontSize: "13px",
                                    border: "1px solid #d4a574",
                                    background: "transparent",
                                    color: "#856404",
                                    borderRadius: "6px",
                                    cursor: "pointer",
                                  }}
                                >
                                  No
                                </button>
                                <button
                                  onClick={async () => {
                                    setMessage(
                                      "remind me what stage of development we are in please?"
                                    );
                                    setShowStatusPrompt(false);
                                    setStatusPromptDismissed(true);
                                    setTimeout(() => {
                                      const form = document.getElementById(
                                        "messageForm"
                                      ) as HTMLFormElement;
                                      form?.requestSubmit();
                                    }, 100);
                                  }}
                                  style={{
                                    padding: "6px 12px",
                                    fontSize: "13px",
                                    border: "none",
                                    background: "#856404",
                                    color: "white",
                                    borderRadius: "6px",
                                    cursor: "pointer",
                                    fontWeight: "500",
                                  }}
                                >
                                  Yes
                                </button>
                              </div>
                            </div>
                          )}

                          {messages.map((msg, idx) => (
                            <div
                              key={idx}
                              style={{
                                marginBottom: "16px",
                                display: "flex",
                                justifyContent:
                                  msg.sender === "user"
                                    ? "flex-end"
                                    : "flex-start",
                                animation: "fadeIn 0.3s ease-out",
                              }}
                            >
                              <div
                                className={
                                  msg.sender === "ai"
                                    ? "glass-message-ai glass-refract"
                                    : "glass-message glass-refract"
                                }
                                style={{
                                  maxWidth: "75%",
                                  padding: "12px 16px",
                                  borderRadius: "24px",
                                  fontSize: "14px",
                                  lineHeight: "1.5",
                                  color: "#2c2c2c",
                                  position: "relative",
                                  background: msg.sender === "user" 
                                    ? "linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(16, 185, 129, 0.15) 100%)"
                                    : msg.subagent
                                    ? "linear-gradient(135deg, rgba(22, 163, 74, 0.1) 0%, rgba(34, 197, 94, 0.1) 100%)"
                                    : undefined,
                                  border: msg.sender === "user"
                                    ? "1px solid rgba(34, 197, 94, 0.3)"
                                    : msg.subagent
                                    ? "1px solid rgba(22, 163, 74, 0.2)"
                                    : undefined
                                }}
                              >
                                {msg.sender === "ai" && (
                                  <div
                                    style={{
                                      fontSize: "11px",
                                      color: msg.subagent ? "#16a34a" : "#0066cc",
                                      fontWeight: "600",
                                      marginBottom: "6px",
                                      letterSpacing: "0.5px",
                                      display: "flex",
                                      alignItems: "center",
                                      gap: "6px",
                                    }}
                                  >
                                    {msg.subagent ? (
                                      <>
                                        <span style={{ color: "#16a34a" }}>🤖 {(msg.subagent_name || 'SUBAGENT').toUpperCase()}</span>
                                        <span style={{ color: "#666", fontSize: "10px" }}>(via Wind Farm Agent)</span>
                                      </>
                                    ) : (
                                      "WIND FARM AGENT"
                                    )}
                                  </div>
                                )}
                                {msg.sender === "user" && (
                                  <div
                                    style={{
                                      fontSize: "11px",
                                      color: "#16a34a",
                                      fontWeight: "600",
                                      marginBottom: "6px",
                                      letterSpacing: "0.5px",
                                    }}
                                  >
                                    YOU
                                  </div>
                                )}
                                {msg.sender === "ai" ? (
                                  <AgentResponse 
                                    message={msg}
                                    isStreaming={idx === messages.length - 1 && (isWorking || isThinking)}
                                    isWorking={isWorking && idx === messages.length - 1}
                                    isThinking={isThinking && idx === messages.length - 1}
                                    currentToolEvents={idx === messages.length - 1 ? currentToolEvents : []}
                                    currentReasoning={idx === messages.length - 1 ? currentReasoning : ""}
                                    showSections={showSections}
                                  />
                                ) : (
                                  msg.text
                                )}

                              </div>
                            </div>
                          ))}
                          {isWaiting && (
                            <div
                              style={{
                                marginBottom: "16px",
                                display: "flex",
                                justifyContent: "flex-start",
                                animation: "fadeIn 0.3s ease-out",
                              }}
                            >
                              <div
                                style={{
                                  padding: "12px 16px",
                                  borderRadius: "24px",
                                  background: "#f0f7ff",
                                  border: "1px solid #d0e7ff",
                                  boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                                  display: "flex",
                                  gap: "6px",
                                  alignItems: "center",
                                }}
                              >
                                <div
                                  style={{
                                    width: "8px",
                                    height: "8px",
                                    backgroundColor: "#0066cc",
                                    borderRadius: "50%",
                                    animation:
                                      "bounce 1.4s ease-in-out infinite",
                                  }}
                                ></div>
                                <div
                                  style={{
                                    width: "8px",
                                    height: "8px",
                                    backgroundColor: "#0066cc",
                                    borderRadius: "50%",
                                    animation:
                                      "bounce 1.4s ease-in-out 0.2s infinite",
                                  }}
                                ></div>
                                <div
                                  style={{
                                    width: "8px",
                                    height: "8px",
                                    backgroundColor: "#0066cc",
                                    borderRadius: "50%",
                                    animation:
                                      "bounce 1.4s ease-in-out 0.4s infinite",
                                  }}
                                ></div>
                              </div>
                            </div>
                          )}
                          <div ref={messagesEndRef} />
                          {showScrollButton && (
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                scrollToBottom();
                              }}
                              style={{
                                position: "sticky",
                                bottom: "8px",
                                left: "50%",
                                transform: "translateX(-50%)",
                                width: "24px",
                                height: "24px",
                                background: "transparent",
                                border: "none",
                                color: "#0066cc",
                                fontSize: "20px",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                animation:
                                  "smoothBounce 1.5s ease-in-out infinite",
                                zIndex: 10,
                                marginTop: "-48px",
                              }}
                            >
                              ↓
                            </button>
                          )}
                          <style>{`
                                                    @keyframes fadeText {
                                                        0%, 100% { opacity: 1; }
                                                        50% { opacity: 0.6; }
                                                    }
                                                    @keyframes smoothBounce {
                                                        0%, 100% { 
                                                            transform: translateY(0);
                                                            opacity: 0.7;
                                                        }
                                                        50% { 
                                                            transform: translateY(8px);
                                                            opacity: 1;
                                                        }
                                                    }
                                                    @keyframes pulse {
                                                        0%, 100% { opacity: 1; transform: scale(1); }
                                                        50% { opacity: 0.3; transform: scale(0.8); }
                                                    }
                                                    @keyframes fadeIn {
                                                        from { opacity: 0; transform: translateY(10px); }
                                                        to { opacity: 1; transform: translateY(0); }
                                                    }
                                                    @keyframes bounce {
                                                        0%, 60%, 100% { transform: translateY(0); }
                                                        30% { transform: translateY(-10px); }
                                                    }
                                                `}</style>
                        </div>
                        <div
                          className="glass-input"
                          style={{ padding: "0px 1px", flexShrink: 0 }}
                        >
                          {!currentProjectId && (
                            <div
                              className="glass-message-warning glass-refract"
                              style={{
                                padding: "10px 14px",
                                borderRadius: "12px",
                                fontSize: "13px",
                                color: "#856404",
                                marginBottom: "12px",
                              }}
                            >
                              ⚠️ Please create or select a project from the top menu
                            </div>
                          )}
                          {!pollingConnected && (
                            <div
                              className="glass-message-warning glass-refract"
                              style={{
                                padding: "10px 14px",
                                borderRadius: "12px",
                                fontSize: "13px",
                                color: "#856404",
                                marginBottom: "12px",
                              }}
                            >
                              🔌 {pollingError || 'Initializing asset monitor...'}
                            </div>
                          )}
                          <form
                            id="messageForm"
                            onSubmit={(e) => {
                              e.preventDefault();
                              if (currentProjectId) {
                                submitMessageForm();
                              }
                            }}
                            style={{ width: "100%" }}
                          >
                            <div style={{ width: "100%", padding: "10px 0px 0px 0px"}}>
                              <textarea
                                value={message}
                                onChange={(e) => {
                                  if (currentProjectId) {
                                    setMessage(e.target.value);
                                  }
                                }}
                                placeholder={
                                  currentProjectId
                                    ? "Send a message..."
                                    : "Create a project to start chatting..."
                                }
                                disabled={!currentProjectId}
                                readOnly={!currentProjectId}
                                rows={3}
                                style={{
                                  width: "100%",
                                  minHeight: "60px",
                                  maxHeight: "200px",
                                  padding: "10px 10px",
                                  border: "1px solid #d5dbdb",
                                  borderRadius: "8px",
                                  fontSize: "14px",
                                  fontFamily: "inherit",
                                  resize: "vertical",
                                  outline: "none",
                                  background: currentProjectId ? "white" : "#f9f9f9",
                                  color: currentProjectId ? "#2c2c2c" : "#999",
                                  boxSizing: "border-box"
                                }}
                                onFocus={(e) => {
                                  if (currentProjectId) {
                                    e.target.style.borderColor = "#0066cc";
                                    e.target.style.boxShadow = "0 0 0 2px rgba(0, 102, 204, 0.2)";
                                  }
                                }}
                                onBlur={(e) => {
                                  e.target.style.borderColor = "#d5dbdb";
                                  e.target.style.boxShadow = "none";
                                }}
                              />
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "6px" }}>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const newValue = !showSections;
                                    setShowSections(newValue);
                                    localStorage.setItem('showChatSections', newValue ? 'true' : 'false');
                                  }}
                                  style={{
                                    border: "1px solid #e0e0e0",
                                    background: showSections ? "#0066cc" : "white",
                                    borderRadius: "6px",
                                    padding: "8px 16px",
                                    fontSize: "12px",
                                    cursor: "pointer",
                                    color: showSections ? "white" : "#666",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "4px"
                                  }}
                                  title={showSections ? "Hide sections" : "Highlight sections"}
                                >
                                  📋 {showSections ? "Hide" : "Highlight"} Sections
                                </button>
                                <button
                                  type="submit"
                                  disabled={!message.trim() || !currentProjectId}
                                  style={{
                                    border: "none",
                                    background: (message.trim() && currentProjectId) ? "#0066cc" : "#e0e0e0",
                                    borderRadius: "6px",
                                    padding: "8px 16px",
                                    cursor: (message.trim() && currentProjectId) ? "pointer" : "not-allowed",
                                    fontSize: "14px",
                                    color: (message.trim() && currentProjectId) ? "white" : "#999",
                                    fontWeight: "500",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "4px"
                                  }}
                                >
                                  Send →
                                </button>
                              </div>
                            </div>
                          </form>
                        </div>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          </div>
        }
        maxContentWidth={Number.MAX_VALUE}
        disableContentPaddings
      />
      <Modal
        visible={showLocationModal}
        onDismiss={() => setShowLocationModal(false)}
        header="Analyze Location"
      >
        {selectedLocation && (
          <SpaceBetween size="l">
            <Box>
              <Box variant="awsui-key-label">Coordinates</Box>
              <div>Latitude: {selectedLocation.lat.toFixed(4)}</div>
              <div>Longitude: {selectedLocation.lon.toFixed(4)}</div>
            </Box>
            <Box>
              Would you like to analyze this location for buildable land?
            </Box>
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => setShowLocationModal(false)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  if (selectedLocation) {
                    setMessage(
                      `Analyze this location (${selectedLocation.lat.toFixed(
                        4
                      )}, ${selectedLocation.lon.toFixed(
                        4
                      )}) for buildable land?`
                    );
                    setShowLocationModal(false);
                    setTimeout(() => {
                      const form = document.getElementById(
                        "messageForm"
                      ) as HTMLFormElement;
                      if (form) form.requestSubmit();
                    }, 100);
                  }
                }}
              >
                Analyze
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        )}
      </Modal>
      <Modal
        visible={showAssetModal}
        onDismiss={() => {
          setShowAssetModal(false);
          setSelectedAsset(null);
        }}
        header={selectedAsset?.path.split("/").pop() || "Asset"}
      >
        {selectedAsset && (
          <div
            className="glass-message glass-refract"
            style={{
              minHeight: "400px",
              borderRadius: "16px",
              padding: "16px",
            }}
          >
            {selectedAsset.path.endsWith(".html") && (
              <iframe
                src={selectedAsset.url}
                style={{
                  width: "100%",
                  height: "600px",
                  border: "none",
                  borderRadius: "8px",
                }}
              />
            )}
            {selectedAsset.path.endsWith(".png") && (
              <img
                src={selectedAsset.url}
                style={{ maxWidth: "100%", borderRadius: "8px" }}
                alt={selectedAsset.path}
              />
            )}
            {selectedAsset.path.endsWith(".pdf") && (
              <iframe
                src={selectedAsset.url}
                style={{
                  width: "100%",
                  height: "600px",
                  border: "none",
                  borderRadius: "8px",
                }}
              />
            )}
            {selectedAsset.path.endsWith(".geojson") && (
              <div>
                <iframe
                  src={selectedAsset.url}
                  style={{
                    width: "100%",
                    height: "600px",
                    border: "none",
                    borderRadius: "8px",
                  }}
                />
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
};

export default Chat;
