"use client";

import { useEffect, useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Phone,
  PhoneOff,
  Mic,
  MicOff,
  User,
  Bot,
  Clock,
} from "lucide-react";
import { formatDuration } from "@/lib/utils";
import type { CallLog } from "@/types";

interface ActiveCallCardProps {
  call: CallLog | null;
  status: string | null;
  transcript: Array<{ speaker: string; text: string }>;
  isRecording: boolean;
  audioLevel: number;
  onEndCall: () => void;
  onToggleMic: () => void;
}

export function ActiveCallCard({
  call,
  status,
  transcript,
  isRecording,
  audioLevel,
  onEndCall,
  onToggleMic,
}: ActiveCallCardProps) {
  const [duration, setDuration] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Update duration every second
  useEffect(() => {
    if (!call) {
      setDuration(0);
      return;
    }

    const startTime = call.started_at ? new Date(call.started_at).getTime() : Date.now();
    const interval = setInterval(() => {
      setDuration(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [call]);

  // Auto-scroll transcript
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  if (!call) {
    return (
      <Card className="border-dashed">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Phone className="h-5 w-5" />
            Active Call
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Phone className="h-12 w-12 mb-4 opacity-20" />
            <p>No active call</p>
            <p className="text-sm">Select a patient from the queue to start a call</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-green-500/50 bg-green-50/30 dark:bg-green-900/10">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <div className="relative">
              <Phone className="h-5 w-5 text-green-600" />
              <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            </div>
            Active Call
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="success" className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(duration)}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Patient Info */}
        <div className="rounded-md bg-background p-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">{call.patient_name}</p>
              <p className="text-sm text-muted-foreground">{call.phone}</p>
            </div>
            <Badge variant="outline">Priority {call.priority_bucket}</Badge>
          </div>
        </div>

        {/* Status */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Status</span>
          <span className="font-medium">{status || "Connected"}</span>
        </div>

        <Separator />

        {/* Audio Controls */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              variant={isRecording ? "default" : "outline"}
              size="sm"
              onClick={onToggleMic}
            >
              {isRecording ? (
                <>
                  <Mic className="h-4 w-4 mr-1" />
                  Speaking
                </>
              ) : (
                <>
                  <MicOff className="h-4 w-4 mr-1" />
                  Muted
                </>
              )}
            </Button>
            {isRecording && (
              <div className="flex items-center gap-1 h-6">
                {[...Array(5)].map((_, i) => (
                  <div
                    key={i}
                    className="audio-bar w-1 bg-green-500 rounded-full"
                    style={{
                      height: `${Math.max(4, audioLevel * 24 * (0.5 + Math.random() * 0.5))}px`,
                    }}
                  />
                ))}
              </div>
            )}
          </div>
          <Button variant="destructive" size="sm" onClick={onEndCall}>
            <PhoneOff className="h-4 w-4 mr-1" />
            End Call
          </Button>
        </div>

        <Separator />

        {/* Live Transcript */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Live Transcript</h4>
          <ScrollArea className="h-[200px] rounded-md border bg-background p-3">
            <div ref={scrollRef} className="space-y-3">
              {transcript.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Waiting for conversation...
                </p>
              ) : (
                transcript.map((entry, index) => (
                  <div
                    key={index}
                    className={`flex gap-2 ${
                      entry.speaker === "ai" ? "justify-start" : "justify-end"
                    }`}
                  >
                    {entry.speaker === "ai" && (
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                        <Bot className="h-3 w-3" />
                      </div>
                    )}
                    <div
                      className={`rounded-lg px-3 py-2 text-sm max-w-[80%] ${
                        entry.speaker === "ai"
                          ? "bg-muted"
                          : "bg-primary text-primary-foreground"
                      }`}
                    >
                      {entry.text}
                    </div>
                    {entry.speaker === "patient" && (
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary">
                        <User className="h-3 w-3" />
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
}
