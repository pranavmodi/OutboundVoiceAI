"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  QueueStatusCard,
  PatientQueueCard,
  ActiveCallCard,
  CallHistoryCard,
  DispatcherEventsCard,
} from "@/components/dashboard";
import { SimulationConsole, OperatorConsole } from "@/components/console";
import { useApi } from "@/hooks/useApi";
import { useDashboardWS, useVoiceWS } from "@/hooks/useWebSocket";
import { useAudio } from "@/hooks/useAudio";
import {
  Phone,
  LayoutDashboard,
  Terminal,
  Settings,
  ChevronDown,
  Circle,
} from "lucide-react";
import type { Patient, CallLog, QueueState, SystemSettings } from "@/types";

export default function Dashboard() {
  // API hooks
  const api = useApi();

  // Dashboard WebSocket (receives queue_update + dispatch_call from backend)
  const dashboard = useDashboardWS();

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

  // Settings state
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [timezones, setTimezones] = useState<string[]>([]);

  // Call mode: "web" (browser audio) or "twilio" (real phone call)
  const [callMode, setCallMode] = useState<string>("web");

  // Operator section collapsed state
  const [operatorOpen, setOperatorOpen] = useState(false);

  // Load initial data - only once
  useEffect(() => {
    if (isLoaded) return;

    const loadData = async () => {
      const [status, patientList, callList, settingsData, tzList] = await Promise.all([
        api.getStatus(),
        api.getOutboundQueue(),
        api.getCalls(),
        api.getSettings(),
        api.getTimezones(),
      ]);

      if (status) {
        setQueueState(status.queue_state);
        setActiveCall(status.active_call);
      }
      setPatients(patientList);
      setCalls(callList);
      setSettings(settingsData);
      setTimezones(tzList);
      setIsLoaded(true);
    };

    loadData();
  }, [isLoaded, api]);

  // Sync queue state from dashboard WebSocket (replaces REST polling)
  useEffect(() => {
    if (dashboard.queueState) setQueueState(dashboard.queueState);
  }, [dashboard.queueState]);

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
      voiceRef.current.sendAudio(data);
    });
  }, [voice, audio]);

  // Handle call start
  const handleCallPatient = useCallback(async (patientId: string) => {
    const patient = patients.find(p => p.patient_id === patientId);
    setCallingPatientName(patient?.name || "Patient");
    setCallStartTime(Date.now());
    setLastCallInfo(null);

    if (!voice.connected) {
      voice.connect();
      for (let i = 0; i < 20; i++) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        if (voiceRef.current.connected) break;
      }
    }

    if (callMode === "web") {
      await audio.startRecording();
      await new Promise((resolve) => setTimeout(resolve, 200));
    }

    voice.startCall(patientId, callMode);
  }, [voice, audio, patients, callMode]);

  // Stop recording when call ends
  const prevActiveRef = useRef(false);
  useEffect(() => {
    const wasActive = prevActiveRef.current;
    const nowActive = voice.isCallActive;
    prevActiveRef.current = nowActive;
    if (wasActive && !nowActive) {
      audio.stopRecording();
    }
  }, [voice.isCallActive, audio]);

  // React to backend dispatch_call commands
  useEffect(() => {
    if (!dashboard.dispatchedPatient) return;
    if (voice.isCallActive) {
      dashboard.clearDispatch();
      return;
    }
    const { patient_id } = dashboard.dispatchedPatient;
    dashboard.clearDispatch();
    handleCallPatient(patient_id);
  }, [dashboard.dispatchedPatient, dashboard.clearDispatch, voice.isCallActive, handleCallPatient]);

  // Handle call end
  const handleEndCall = useCallback(() => {
    const duration = callStartTime ? Math.floor((Date.now() - callStartTime) / 1000) : 0;
    setLastCallInfo({
      patientName: callingPatientName,
      duration,
    });

    voice.endCall();
    audio.stopRecording();
    setActiveCall(null);
    setCallStartTime(null);

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

  // Simulation apply handler
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleApplySimulation = useCallback(async (config: any) => {
    const result = await api.applySimulation(config);
    if (result) {
      if (result.queue_state) setQueueState(result.queue_state);
      const patientList = await api.getOutboundQueue();
      setPatients(patientList);
      const callList = await api.getCalls();
      setCalls(callList);
    }
  }, [api]);

  // Settings handlers
  const handleSetSystemEnabled = useCallback(async (enabled: boolean) => {
    const newSettings = await api.setSystemEnabled(enabled);
    if (newSettings) setSettings(newSettings);
  }, [api]);

  const handleUpdateBusinessHours = useCallback(async (businessHours: SystemSettings["business_hours"]) => {
    const newSettings = await api.updateBusinessHours(businessHours);
    if (newSettings) setSettings(newSettings);
  }, [api]);

  const handleUpdateQueueThresholds = useCallback(async (thresholds: SystemSettings["queue_thresholds"]) => {
    const newSettings = await api.updateQueueThresholds(thresholds);
    if (newSettings) setSettings(newSettings);
  }, [api]);

  const handleSetAllowLiveCalls = useCallback(async (allowed: boolean) => {
    const newSettings = await api.setAllowLiveCalls(allowed);
    if (newSettings) setSettings(newSettings);
  }, [api]);

  const handleUpdateAllowedPhones = useCallback(async (phones: string[]) => {
    const newSettings = await api.updateAllowedPhones(phones);
    if (newSettings) setSettings(newSettings);
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
      <header className="sticky top-0 z-50 border-b bg-card/80 backdrop-blur-lg">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              <Phone className="h-4 w-4" />
            </div>
            <div className="leading-tight">
              <h1 className="text-base font-semibold tracking-tight">Outbound Voice AI</h1>
              <p className="text-xs text-muted-foreground">Precise Imaging</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Connection indicator */}
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {dashboard.connected ? (
                <>
                  <Circle className="h-2 w-2 fill-emerald-500 text-emerald-500 status-dot" />
                  <span className="hidden sm:inline">Connected</span>
                </>
              ) : (
                <>
                  <Circle className="h-2 w-2 fill-red-500 text-red-500" />
                  <span className="hidden sm:inline">Disconnected</span>
                </>
              )}
            </div>

            {/* Call active badge */}
            {voice.isCallActive && (
              <Badge variant="success" className="flex items-center gap-1.5 shadow-sm">
                <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse" />
                Call Active
              </Badge>
            )}

            {/* System status */}
            {settings && (
              <Badge
                variant={settings.system_enabled ? "default" : "outline"}
                className="hidden sm:flex"
              >
                {settings.system_enabled ? "System On" : "System Off"}
              </Badge>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {/* Error Display */}
        {(api.error || voice.error || audio.error) && (
          <div className="mb-6 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive animate-in">
            {api.error || voice.error || audio.error}
          </div>
        )}

        <Tabs defaultValue="dashboard" className="space-y-8">
          <TabsList className="inline-flex h-10 rounded-lg bg-muted p-1">
            <TabsTrigger value="dashboard" className="flex items-center gap-2 rounded-md px-4 text-sm">
              <LayoutDashboard className="h-4 w-4" />
              Dashboard
            </TabsTrigger>
            <TabsTrigger value="simulation" className="flex items-center gap-2 rounded-md px-4 text-sm">
              <Terminal className="h-4 w-4" />
              Simulation
            </TabsTrigger>
          </TabsList>

          {/* Dashboard Tab */}
          <TabsContent value="dashboard" className="space-y-8 animate-in">
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Left Column */}
              <div className="space-y-6">
                <QueueStatusCard queueState={queueState} />
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

            {/* Dispatcher Events - full width */}
            <DispatcherEventsCard events={dashboard.dispatcherEvents} />

            {/* Operator Settings - collapsible */}
            <Collapsible open={operatorOpen} onOpenChange={setOperatorOpen}>
              <Card>
                <CollapsibleTrigger asChild>
                  <CardHeader className="cursor-pointer select-none hover:bg-muted/50 transition-colors rounded-t-lg">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2 text-lg">
                        <Settings className="h-5 w-5" />
                        System Settings
                      </CardTitle>
                      <div className="flex items-center gap-3">
                        {settings && (
                          <Badge
                            variant={settings.system_enabled ? "success" : "outline"}
                            className="text-xs"
                          >
                            {settings.system_enabled ? "Enabled" : "Disabled"}
                          </Badge>
                        )}
                        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${operatorOpen ? "rotate-180" : ""}`} />
                      </div>
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent className="pt-0">
                    <OperatorConsole
                      settings={settings}
                      timezones={timezones}
                      onSetSystemEnabled={handleSetSystemEnabled}
                      onUpdateBusinessHours={handleUpdateBusinessHours}
                      onUpdateQueueThresholds={handleUpdateQueueThresholds}
                      onSetAllowLiveCalls={handleSetAllowLiveCalls}
                      onUpdateAllowedPhones={handleUpdateAllowedPhones}
                    />
                  </CardContent>
                </CollapsibleContent>
              </Card>
            </Collapsible>
          </TabsContent>

          {/* Simulation Tab */}
          <TabsContent value="simulation" className="animate-in">
            <SimulationConsole
              onApplySimulation={handleApplySimulation}
              callMode={callMode}
              onCallModeChange={setCallMode}
            />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
