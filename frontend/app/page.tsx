"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  QueueStatusCard,
  PatientQueueCard,
  ActiveCallCard,
  CallHistoryCard,
} from "@/components/dashboard";
import { useApi } from "@/hooks/useApi";
import { useVoiceWS } from "@/hooks/useWebSocket";
import { useAudio } from "@/hooks/useAudio";
import { Phone, Wifi, WifiOff } from "lucide-react";
import type { Patient, CallLog, QueueState } from "@/types";

export default function Dashboard() {
  // API hooks
  const api = useApi();

  // Voice WebSocket
  const voice = useVoiceWS();

  // Audio hooks
  const audio = useAudio();

  // State
  const [queueState, setQueueState] = useState<QueueState | null>(null);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [calls, setCalls] = useState<CallLog[]>([]);
  const [activeCall, setActiveCall] = useState<CallLog | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [lastCallInfo, setLastCallInfo] = useState<{ patientName: string; duration: number } | null>(null);
  const [callStartTime, setCallStartTime] = useState<number | null>(null);
  const [callingPatientName, setCallingPatientName] = useState<string>("");

  // Load initial data - only once
  useEffect(() => {
    if (isLoaded) return;

    const loadData = async () => {
      const [status, patientList, callList] = await Promise.all([
        api.getStatus(),
        api.getOutboundQueue(),
        api.getCalls(),
      ]);

      if (status) {
        setQueueState(status.queue_state);
        setActiveCall(status.active_call);
      }
      setPatients(patientList);
      setCalls(callList);
      setIsLoaded(true);
    };

    loadData();
  }, [isLoaded, api]);

  // Poll queue state every 10 seconds
  useEffect(() => {
    const interval = setInterval(async () => {
      const state = await api.getQueueState();
      if (state) setQueueState(state);
    }, 10000);

    return () => clearInterval(interval);
  }, []);

  // Store refs to always have latest functions
  const voiceRef = useRef(voice);
  const audioRef = useRef(audio);
  voiceRef.current = voice;
  audioRef.current = audio;

  // Set up audio callbacks - only once
  const audioSetupRef = useRef(false);
  useEffect(() => {
    if (audioSetupRef.current) return;
    audioSetupRef.current = true;

    voice.onAudioReceived((audioData) => {
      audioRef.current.playAudio(audioData);
    });

    audio.onAudioData((data) => {
      // Use ref to always get latest sendAudio function
      voiceRef.current.sendAudio(data);
    });
  }, [voice, audio]);

  // Handle call start
  const handleCallPatient = useCallback(async (patientId: string) => {
    // Find patient name
    const patient = patients.find(p => p.patient_id === patientId);
    setCallingPatientName(patient?.name || "Patient");
    setCallStartTime(Date.now());
    setLastCallInfo(null); // Clear last call info when starting new call

    // Connect to voice WebSocket if not connected
    if (!voice.connected) {
      voice.connect();
      // Wait for connection with retry
      for (let i = 0; i < 20; i++) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        if (voiceRef.current.connected) break;
      }
    }

    // Start recording first (so we're ready when AI responds)
    await audio.startRecording();

    // Small delay to ensure audio is flowing
    await new Promise((resolve) => setTimeout(resolve, 200));

    // Start the call
    voice.startCall(patientId);
  }, [voice, audio, patients]);

  // Handle call end
  const handleEndCall = useCallback(() => {
    // Save last call info before ending
    const duration = callStartTime ? Math.floor((Date.now() - callStartTime) / 1000) : 0;
    setLastCallInfo({
      patientName: callingPatientName,
      duration,
    });

    voice.endCall();
    audio.stopRecording();
    setActiveCall(null);
    setCallStartTime(null);

    // Refresh data
    api.getCalls().then(setCalls);
    api.getOutboundQueue().then(setPatients);
  }, [voice, audio, api, callStartTime, callingPatientName]);

  // Handle mic toggle
  const handleToggleMic = useCallback(async () => {
    if (audio.isRecording) {
      audio.stopRecording();
    } else {
      await audio.startRecording();
    }
  }, [audio]);

  // Queue simulation handlers
  const handleSimulateBusy = useCallback(async () => {
    const state = await api.simulateBusyQueue();
    if (state) setQueueState(state);
  }, [api]);

  const handleSimulateQuiet = useCallback(async () => {
    const state = await api.simulateQuietQueue();
    if (state) setQueueState(state);
  }, [api]);

  const handleSimulateAmiFailure = useCallback(async () => {
    const state = await api.simulateAmiFailure();
    if (state) setQueueState(state);
  }, [api]);

  const handleSimulateAmiRecovery = useCallback(async () => {
    const state = await api.simulateAmiRecovery();
    if (state) setQueueState(state);
  }, [api]);

  // Refresh handlers
  const handleRefreshPatients = useCallback(async () => {
    const patientList = await api.getOutboundQueue();
    setPatients(patientList);
  }, [api]);

  const handleRefreshCalls = useCallback(async () => {
    const callList = await api.getCalls();
    setCalls(callList);
  }, [api]);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Phone className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-xl font-semibold">AI Outbound Voice Orchestrator</h1>
                <p className="text-sm text-muted-foreground">
                  Precise Imaging Scheduling Assistant
                </p>
              </div>
            </div>
            {voice.isCallActive && (
              <Badge variant="success" className="flex items-center gap-1">
                <Wifi className="h-3 w-3" />
                Call Active
              </Badge>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        {/* Error Display */}
        {(api.error || voice.error || audio.error) && (
          <div className="mb-4 rounded-md bg-destructive/10 p-4 text-destructive">
            {api.error || voice.error || audio.error}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left Column */}
          <div className="space-y-6">
            <QueueStatusCard
              queueState={queueState}
              onSimulateBusy={handleSimulateBusy}
              onSimulateQuiet={handleSimulateQuiet}
              onSimulateAmiFailure={handleSimulateAmiFailure}
              onSimulateAmiRecovery={handleSimulateAmiRecovery}
            />
            <PatientQueueCard
              patients={patients}
              onCallPatient={handleCallPatient}
              onRefresh={handleRefreshPatients}
              isCallActive={voice.isCallActive}
              outboundAllowed={queueState?.outbound_allowed ?? false}
            />
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            <ActiveCallCard
              call={voice.isCallActive ? ({
                call_id: "active",
                patient_id: "",
                patient_name: callingPatientName || "Patient",
                phone: "",
                order_id: null,
                priority_bucket: 0,
                started_at: callStartTime ? new Date(callStartTime).toISOString() : new Date().toISOString(),
                ended_at: null,
                duration_seconds: 0,
                outcome: "in_progress",
                transfer_attempted: false,
                transfer_success: false,
                voicemail_left: false,
                sms_sent: false,
                queue_snapshot: null,
                transcript: [],
                error_code: null,
                error_message: null,
              } as CallLog) : null}
              status={voice.callStatus}
              transcript={voice.transcript}
              isRecording={audio.isRecording}
              audioLevel={audio.audioLevel}
              onEndCall={handleEndCall}
              onToggleMic={handleToggleMic}
              lastCallInfo={lastCallInfo}
            />
            <CallHistoryCard calls={calls} onRefresh={handleRefreshCalls} />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t mt-8">
        <div className="container mx-auto px-4 py-4">
          <p className="text-center text-sm text-muted-foreground">
            AI Outbound Voice Orchestrator - Mock Mode
          </p>
        </div>
      </footer>
    </div>
  );
}
