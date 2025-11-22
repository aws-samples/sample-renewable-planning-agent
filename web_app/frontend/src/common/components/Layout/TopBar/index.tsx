import { TopNavigation, Input, Modal, Box, SpaceBetween, Button } from "@cloudscape-design/components";
import { useEffect, useState } from "react";
import Logo from "./logo.png";

const APP_NAME = "Wind Farm Development Agent";
const API_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '');

// Default user for demo purposes
const DEFAULT_USER = "demo@example.com";

const TopBar = () => {
    const [email] = useState<string>(DEFAULT_USER);
    const [showProjectModal, setShowProjectModal] = useState(false);
    const [projectId, setProjectId] = useState<string>(() => localStorage.getItem('projectId') || '');
    const [newProjectName, setNewProjectName] = useState('');
    const [projects, setProjects] = useState<Array<{ id: string; name: string }>>(() => {
        const saved = localStorage.getItem('projects');
        return saved ? JSON.parse(saved) : [];
    });

    useEffect(() => {
        // Fetch projects for user
        const fetchProjects = async () => {
            try {
                const response = await fetch(`${API_URL}/projects/${email}`);
                const fetchedProjects = await response.json();
                
                // Merge with local projects
                const localProjects = JSON.parse(localStorage.getItem('projects') || '[]');
                const allProjects = [...fetchedProjects, ...localProjects];
                
                // Remove duplicates by id
                const uniqueProjects = allProjects.filter((project, index, self) => 
                    index === self.findIndex(p => p.id === project.id)
                );
                
                setProjects(uniqueProjects);
                localStorage.setItem('projects', JSON.stringify(uniqueProjects));
            } catch (error) {
                console.error('Failed to fetch projects:', error);
            }
        };
        fetchProjects();
    }, [email]);

    // Initialize projectId from localStorage and listen for changes
    useEffect(() => {
        // Set initial value from localStorage
        const storedProjectId = localStorage.getItem('projectId');
        if (storedProjectId && storedProjectId !== projectId) {
            setProjectId(storedProjectId);
        }
        
        const handleStorageChange = () => {
            const newProjectId = localStorage.getItem('projectId') || '';
            setProjectId(newProjectId);
        };
        
        window.addEventListener('storage', handleStorageChange);
        return () => window.removeEventListener('storage', handleStorageChange);
    }, []);

    const generateUUID = () => {
        // Fallback UUID generator for browsers that don't support crypto.randomUUID
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        // Fallback implementation
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    };

    const handleProjectIdSubmit = () => {
        if (newProjectName) {
            const newId = generateUUID();
            localStorage.setItem('projectId', newId);
            setProjectId(newId);
            // Add to projects list
            const newProject = { id: newId, name: newProjectName };
            setProjects(prev => {
                const updated = [...prev, newProject];
                localStorage.setItem('projects', JSON.stringify(updated));
                return updated;
            });
            setNewProjectName('');
            setShowProjectModal(false);
            window.dispatchEvent(new Event('storage'));
        }
    };

    const selectProject = (id: string) => {
        localStorage.setItem('projectId', id);
        setProjectId(id);
        setShowProjectModal(false);
        window.dispatchEvent(new Event('storage'));
    };

    return (
        <div>
            <TopNavigation
                identity={{
                    href: "/",
                    title: APP_NAME,
                    logo: {
                        src: Logo,
                        alt: APP_NAME,
                    },
                }}
                utilities={[
                    {
                        type: "menu-dropdown",
                        text: projectId ? (projects.find(p => p.id === projectId)?.name || `Project: ${projectId}`) : "Select Project",
                        iconName: "folder",
                        onItemClick: ({ detail }) => {
                            if (detail.id === "new-project") {
                                setShowProjectModal(true);
                            } else {
                                selectProject(detail.id);
                            }
                        },
                        items: [
                            ...(projects.length > 0 ? [
                                {
                                    id: "projects-header",
                                    text: "Your Projects",
                                    disabled: true
                                },
                                ...projects.map(project => ({
                                    id: project.id,
                                    text: project.name
                                }))
                            ] : []),
                            {
                                id: "new-project",
                                text: "Create New Project",
                                iconName: "add-plus"
                            }
                        ]
                    },
                    {
                        type: "button",
                        iconName: "user-profile",
                        text: email,
                    },
                ]}
            />
            <Modal
                visible={showProjectModal}
                onDismiss={() => setShowProjectModal(false)}
                header="Create New Project"
            >
                <SpaceBetween size="l">
                    <Box>
                        <SpaceBetween size="s">
                            <Input
                                value={newProjectName}
                                onChange={({ detail }) => setNewProjectName(detail.value)}
                                placeholder="Enter project name (e.g., Texas Panhandle Wind Farm)"
                            />
                            <Button onClick={handleProjectIdSubmit} variant="primary">
                                Create Project
                            </Button>
                        </SpaceBetween>
                    </Box>
                    {projects.length > 0 && (
                        <Box>
                            <Box variant="h3">Recent Projects</Box>
                            <SpaceBetween size="xs">
                                {projects.map((project) => (
                                    <Button
                                        key={project.id}
                                        onClick={() => selectProject(project.id)}
                                        variant="normal"
                                        fullWidth
                                    >
                                        {project.name}
                                    </Button>
                                ))}
                            </SpaceBetween>
                        </Box>
                    )}
                </SpaceBetween>
            </Modal>
        </div>
    );
};

export default TopBar;
