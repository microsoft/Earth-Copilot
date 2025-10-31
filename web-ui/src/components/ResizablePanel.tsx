// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useRef, useEffect, ReactNode } from 'react';

interface ResizablePanelProps {
    children: ReactNode;
    defaultWidth?: number;
    minWidth?: number;
    maxWidth?: number;
    onWidthChange?: (width: number) => void;
    className?: string;
}

const ResizablePanel: React.FC<ResizablePanelProps> = ({
    children,
    defaultWidth = 420,
    minWidth = 300,
    maxWidth = 800,
    onWidthChange,
    className = ''
}) => {
    const [width, setWidth] = useState(defaultWidth);
    const [isResizing, setIsResizing] = useState(false);
    const panelRef = useRef<HTMLDivElement>(null);
    const startXRef = useRef(0);
    const startWidthRef = useRef(0);

    const handleMouseDown = (e: React.MouseEvent) => {
        e.preventDefault();
        setIsResizing(true);
        startXRef.current = e.clientX;
        startWidthRef.current = width;

        // Add global event listeners
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none';
    };

    const handleMouseMove = (e: MouseEvent) => {
        if (!isResizing) return;

        // Calculate new width (dragging left increases width, dragging right decreases width)
        const deltaX = startXRef.current - e.clientX;
        const newWidth = Math.max(minWidth, Math.min(maxWidth, startWidthRef.current + deltaX));

        setWidth(newWidth);
        onWidthChange?.(newWidth);
    };

    const handleMouseUp = () => {
        setIsResizing(false);
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    };

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
    }, []);

    return (
        <div
            ref={panelRef}
            className={`resizable-panel ${className}`}
            style={{ width: `${width}px` }}
        >
            {/* Resize handle */}
            <div
                className="resize-handle"
                onMouseDown={handleMouseDown}
                onMouseEnter={(e) => {
                    const indicator = e.currentTarget.querySelector('div');
                    if (indicator instanceof HTMLElement) {
                        indicator.style.opacity = '1';
                        indicator.style.backgroundColor = '#007acc';
                        indicator.style.height = '60px';
                        indicator.style.width = '4px';
                    }
                }}
                onMouseLeave={(e) => {
                    if (isResizing) return;
                    const indicator = e.currentTarget.querySelector('div');
                    if (indicator instanceof HTMLElement) {
                        indicator.style.opacity = '0.7';
                        indicator.style.backgroundColor = '#94a3b8';
                        indicator.style.height = '40px';
                        indicator.style.width = '3px';
                    }
                }}
                style={{
                    position: 'absolute',
                    left: 0,
                    top: 0,
                    bottom: 0,
                    width: '12px',
                    cursor: 'ew-resize',
                    backgroundColor: 'transparent',
                    borderLeft: isResizing ? '2px solid #007acc' : 'none',
                    zIndex: 1000,
                    transition: isResizing ? 'none' : 'all 0.2s ease'
                }}
            >
                {/* Visual indicator */}
                <div
                    style={{
                        position: 'absolute',
                        left: '50%',
                        top: '50%',
                        transform: 'translate(-50%, -50%)',
                        width: '3px',
                        height: '40px',
                        backgroundColor: isResizing ? '#007acc' : '#94a3b8',
                        borderRadius: '3px',
                        opacity: isResizing ? 1 : 0.7,
                        transition: isResizing ? 'none' : 'all 0.2s ease',
                        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)'
                    }}
                />
            </div>

            {/* Content */}
            <div style={{ height: '100%' }}>
                {children}
            </div>
        </div>
    );
};

export default ResizablePanel;