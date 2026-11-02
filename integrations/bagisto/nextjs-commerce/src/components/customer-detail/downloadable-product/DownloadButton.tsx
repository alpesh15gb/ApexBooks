"use client";

import { useState } from "react";
import clsx from "clsx";
import { useToast } from "@/providers/ToastProvider";

export default function DownloadButton({ 
    url, 
    fileName, 
    children
}: { 
    url: string; 
    fileName: string; 
    children: React.ReactNode;
}) {
    const [loading, setLoading] = useState(false);
    const { addToast } = useToast();

    const handleDownload = async (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();

        if (!url || loading) return;
        setLoading(true);
        
        try {
            const path = new URL(url, window.location.origin).pathname;
            const match = path.match(/^\/api\/shop\/customer-downloadable-products\/(\d+)\/download$/);
            if (!match) throw new Error('Unsupported purchase download link');
            const response = await fetch(`/api/customer-download?id=${match[1]}`, {
                method: 'GET',
                credentials: 'same-origin',
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                
                if (response.status === 429) {
                    const retryAfter = errorData.retry_after || 'some time';
                    addToast({ 
                        message: `Rate limit exceeded. Please try again after ${retryAfter} seconds.`, 
                        type: "danger" 
                    });
                } else if (response.status === 401) {
                    addToast({ 
                        message: "Unauthorized. Please log in again to download.", 
                        type: "danger" 
                    });
                } else {
                    addToast({ 
                        message: errorData.message || "Failed to download the file. Please try again.", 
                        type: "danger" 
                    });
                }
                return;
            }

            const blob = await response.blob();
            const blobUrl = window.URL.createObjectURL(blob);
            
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = fileName || 'download';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
            
            addToast({ message: "Download started successfully!", type: "success" });
        } catch (error) {
            console.error('Error downloading file:', error);
            addToast({ message: "An unexpected error occurred. Please try again.", type: "danger" });
        } finally {
            setLoading(false);
        }
    };

    return (
        <button type="button" disabled={loading} aria-busy={loading}
            onClick={handleDownload}
            className={clsx(
                "cursor-pointer transition-all relative",
                loading ? "opacity-50 pointer-events-none" : "hover:opacity-80"
            )}
            style={{ minWidth: '84px', minHeight: '22px' }}
        >
            <span className={loading ? "invisible" : ""}>{children}</span>
            {loading && (
                <span className="absolute inset-0 flex items-center justify-center font-outfit font-medium text-xs lg:text-base leading-[20px] lg:leading-[22px] text-primary dark:text-primary-soft animate-pulse whitespace-nowrap">
                    Downloading...
                </span>
            )}
        </button>
    );
}
