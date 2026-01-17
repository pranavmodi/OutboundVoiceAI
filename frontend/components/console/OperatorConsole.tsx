"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Power,
  Clock,
  Settings,
  CheckCircle,
  XCircle,
} from "lucide-react";
import type { SystemSettings, BusinessHours, QueueThresholds } from "@/types";

interface OperatorConsoleProps {
  settings: SystemSettings | null;
  timezones: string[];
  onSetSystemEnabled: (enabled: boolean) => Promise<void>;
  onUpdateBusinessHours: (businessHours: BusinessHours) => Promise<void>;
  onUpdateQueueThresholds: (thresholds: QueueThresholds) => Promise<void>;
}

export function OperatorConsole({
  settings,
  timezones,
  onSetSystemEnabled,
  onUpdateBusinessHours,
  onUpdateQueueThresholds,
}: OperatorConsoleProps) {
  // Local state for form values
  const [businessHoursForm, setBusinessHoursForm] = useState<BusinessHours>({
    start_time: "08:00",
    end_time: "17:00",
    enabled: false,
    timezone: "America/New_York",
  });

  const [thresholdsForm, setThresholdsForm] = useState<QueueThresholds>({
    calls_waiting_threshold: 1,
    oldest_wait_threshold_seconds: 30,
    stable_polls_required: 3,
  });

  // Sync form state with settings when loaded
  useEffect(() => {
    if (settings) {
      setBusinessHoursForm(settings.business_hours);
      setThresholdsForm(settings.queue_thresholds);
    }
  }, [settings]);

  const handleBusinessHoursSubmit = async () => {
    await onUpdateBusinessHours(businessHoursForm);
  };

  const handleThresholdsSubmit = async () => {
    await onUpdateQueueThresholds(thresholdsForm);
  };

  if (!settings) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        {/* System Control */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Power className="h-5 w-5" />
              System Control
            </CardTitle>
            <CardDescription>
              Enable or disable the outbound calling system
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <Label htmlFor="system-enabled">System Status</Label>
                <p className="text-sm text-muted-foreground">
                  {settings.system_enabled
                    ? "System is active and can make calls"
                    : "System is disabled, no calls will be made"}
                </p>
              </div>
              <Switch
                id="system-enabled"
                checked={settings.system_enabled}
                onCheckedChange={onSetSystemEnabled}
              />
            </div>
            <div className="flex items-center gap-2 pt-2">
              <span className="text-sm font-medium">Can Make Calls:</span>
              {settings.can_make_calls ? (
                <Badge variant="success" className="flex items-center gap-1">
                  <CheckCircle className="h-3 w-3" />
                  Yes
                </Badge>
              ) : (
                <Badge variant="destructive" className="flex items-center gap-1">
                  <XCircle className="h-3 w-3" />
                  No
                </Badge>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Business Hours */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Business Hours
            </CardTitle>
            <CardDescription>
              Configure when outbound calls can be made
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <Label htmlFor="business-hours-enabled">Enable Business Hours</Label>
              <Switch
                id="business-hours-enabled"
                checked={businessHoursForm.enabled}
                onCheckedChange={(checked) =>
                  setBusinessHoursForm({ ...businessHoursForm, enabled: checked })
                }
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="start-time">Start Time</Label>
                <Input
                  id="start-time"
                  type="time"
                  value={businessHoursForm.start_time}
                  onChange={(e) =>
                    setBusinessHoursForm({ ...businessHoursForm, start_time: e.target.value })
                  }
                  disabled={!businessHoursForm.enabled}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="end-time">End Time</Label>
                <Input
                  id="end-time"
                  type="time"
                  value={businessHoursForm.end_time}
                  onChange={(e) =>
                    setBusinessHoursForm({ ...businessHoursForm, end_time: e.target.value })
                  }
                  disabled={!businessHoursForm.enabled}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="timezone">Timezone</Label>
              <Select
                value={businessHoursForm.timezone}
                onValueChange={(value) =>
                  setBusinessHoursForm({ ...businessHoursForm, timezone: value })
                }
                disabled={!businessHoursForm.enabled}
              >
                <SelectTrigger id="timezone">
                  <SelectValue placeholder="Select timezone" />
                </SelectTrigger>
                <SelectContent>
                  {timezones.map((tz) => (
                    <SelectItem key={tz} value={tz}>
                      {tz}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center justify-between pt-2">
              <span className="text-sm text-muted-foreground">
                Currently within hours:
              </span>
              {settings.is_within_business_hours ? (
                <Badge variant="success">Yes</Badge>
              ) : (
                <Badge variant="outline">No</Badge>
              )}
            </div>

            <Button onClick={handleBusinessHoursSubmit} className="w-full">
              Save Business Hours
            </Button>
          </CardContent>
        </Card>

        {/* Queue Thresholds */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Queue Thresholds
            </CardTitle>
            <CardDescription>
              Configure when outbound calls are allowed based on queue conditions
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-6 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="calls-waiting">Max Calls Waiting</Label>
                <Input
                  id="calls-waiting"
                  type="number"
                  min="0"
                  value={thresholdsForm.calls_waiting_threshold}
                  onChange={(e) =>
                    setThresholdsForm({
                      ...thresholdsForm,
                      calls_waiting_threshold: parseInt(e.target.value) || 0,
                    })
                  }
                />
                <p className="text-xs text-muted-foreground">
                  Block outbound if more calls waiting
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="oldest-wait">Max Wait Time (seconds)</Label>
                <Input
                  id="oldest-wait"
                  type="number"
                  min="0"
                  value={thresholdsForm.oldest_wait_threshold_seconds}
                  onChange={(e) =>
                    setThresholdsForm({
                      ...thresholdsForm,
                      oldest_wait_threshold_seconds: parseInt(e.target.value) || 0,
                    })
                  }
                />
                <p className="text-xs text-muted-foreground">
                  Block if oldest call waiting longer
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="stable-polls">Stable Polls Required</Label>
                <Input
                  id="stable-polls"
                  type="number"
                  min="1"
                  value={thresholdsForm.stable_polls_required}
                  onChange={(e) =>
                    setThresholdsForm({
                      ...thresholdsForm,
                      stable_polls_required: parseInt(e.target.value) || 1,
                    })
                  }
                />
                <p className="text-xs text-muted-foreground">
                  Consecutive stable polls before allowing
                </p>
              </div>
            </div>

            <Button onClick={handleThresholdsSubmit} className="w-full md:w-auto">
              Save Thresholds
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
