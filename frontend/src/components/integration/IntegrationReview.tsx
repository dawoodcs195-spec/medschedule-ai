"use client";

import React, { useState } from "react";
import { ParsedTopic, ProposedLink } from "@/types";
import {
  Check,
  X,
  Link2,
  GitMerge,
  Sparkles,
  ArrowRight,
  Plus,
  CheckCheck,
  RotateCcw,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

interface IntegrationReviewProps {
  links: ProposedLink[];
  topics: ParsedTopic[];
  onToggleApproval: (id: string) => void;
  onBulkApprove: (approve: boolean) => void;
  onAddCustomLink: (link: ProposedLink) => void;
  onSuggestClinical?: () => Promise<number>;
  onProceed: () => void;
  isLoading?: boolean;
  embeddingEngine: string;
}

export const IntegrationReview: React.FC<IntegrationReviewProps> = ({
  links,
  topics,
  onToggleApproval,
  onBulkApprove,
  onAddCustomLink,
  onSuggestClinical,
  onProceed,
  isLoading = false,
}) => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [srcIdx, setSrcIdx] = useState<number>(0);
  const [tgtIdx, setTgtIdx] = useState<number>(Math.min(1, Math.max(0, topics.length - 1)));
  const [linkType, setLinkType] = useState<"HORIZONTAL" | "VERTICAL">("HORIZONTAL");
  const [customRationale, setCustomRationale] = useState("");
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestMessage, setSuggestMessage] = useState<string | null>(null);
  const [cohortFilter, setCohortFilter] = useState<string>("ALL");

  const cohortKeys = Array.from(new Set(topics.map((t) => t.cohort).filter((c): c is string => !!c))).sort();
  const isMultiCohort = cohortKeys.length > 1;
  const visibleLinks =
    cohortFilter === "ALL"
      ? links
      : links.filter((l) => l.source_cohort === cohortFilter || l.target_cohort === cohortFilter);
  const horizontalLinks = visibleLinks.filter((l) => l.integration_type === "HORIZONTAL");
  const verticalLinks = visibleLinks.filter((l) => l.integration_type === "VERTICAL");
  const approvedCount = links.filter((l) => l.is_approved).length;

  const handleSuggestClinicalClick = async () => {
    if (!onSuggestClinical) return;
    setIsSuggesting(true);
    try {
      const addedCount = await onSuggestClinical();
      setSuggestMessage(
        addedCount > 0
          ? `Added ${addedCount} clinical topic(s) & linked them vertically.`
          : "All matching clinical topics are already linked."
      );
    } finally {
      setIsSuggesting(false);
    }
  };

  const handleCreateCustomLink = () => {
    if (srcIdx === tgtIdx || !topics[srcIdx] || !topics[tgtIdx]) return;
    const s = topics[srcIdx];
    const t = topics[tgtIdx];
    const newLink: ProposedLink = {
      id:
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `custom-${Date.now()}`,
      source_objective_id: s.id ?? null,
      target_objective_id: t.id ?? null,
      source_cohort: s.cohort ?? null,
      target_cohort: t.cohort ?? null,
      source_index: srcIdx,
      target_index: tgtIdx,
      source_topic: s.topic_title,
      target_topic: t.topic_title,
      source_discipline: s.discipline,
      target_discipline: t.discipline,
      integration_type: linkType,
      similarity_score: 0.95,
      is_approved: true,
      rationale:
        customRationale.trim() ||
        (linkType === "HORIZONTAL"
          ? `${s.discipline} ↔ ${t.discipline}`
          : `${s.discipline} → ${t.discipline}`),
    };
    onAddCustomLink(newLink);
    setCustomRationale("");
    setShowAddForm(false);
  };

  const renderLinkList = (items: ProposedLink[], type: "HORIZONTAL" | "VERTICAL") => {
    if (items.length === 0) {
      return (
        <div className="py-12 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
          No {type.toLowerCase()} links found.
        </div>
      );
    }

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[520px] overflow-y-auto pr-1">
        {items.map((link) => {
          const isHoriz = link.integration_type === "HORIZONTAL";
          return (
            <div
              key={link.id}
              onClick={() => onToggleApproval(link.id)}
              className={`group flex items-start justify-between gap-3 p-3.5 rounded-xl border transition-all duration-150 cursor-pointer ${
                link.is_approved
                  ? isHoriz
                    ? "bg-sky-50/50 border-sky-200/90 hover:border-sky-300 dark:bg-sky-950/20 dark:border-sky-800/70"
                    : "bg-purple-50/50 border-purple-200/90 hover:border-purple-300 dark:bg-purple-950/20 dark:border-purple-800/70"
                  : "bg-muted/30 border-border opacity-55 hover:opacity-85"
              }`}
            >
              <div className="space-y-1.5 flex-1 min-w-0">
                <div className="flex items-center gap-1.5 flex-wrap">
                  {isMultiCohort && link.source_cohort && (
                    <Badge variant="slate" className="font-mono text-[10px]">{link.source_cohort}</Badge>
                  )}
                  <Badge variant="sky">{link.source_discipline}</Badge>
                  <span className="text-[11px] text-muted-foreground font-mono">
                    {isHoriz ? "↔" : "→"}
                  </span>
                  {isMultiCohort && !isHoriz && link.target_cohort && (
                    <Badge variant="slate" className="font-mono text-[10px]">{link.target_cohort}</Badge>
                  )}
                  <Badge variant={isHoriz ? "sky" : "purple"}>{link.target_discipline}</Badge>
                  <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                    {(link.similarity_score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-xs font-semibold text-foreground leading-snug">
                  {link.source_topic}{" "}
                  <span className="text-muted-foreground font-normal">
                    {isHoriz ? "&" : "→"}
                  </span>{" "}
                  {link.target_topic}
                </p>
                {link.shared_concepts && link.shared_concepts.length > 0 && (
                  <p className="text-[11px] text-muted-foreground">
                    Shared: {link.shared_concepts.map((c) => c.replace(/_/g, " ")).join(", ")}
                  </p>
                )}
              </div>

              <Button
                variant={link.is_approved ? "emerald" : "outline"}
                size="icon-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleApproval(link.id);
                }}
                aria-label={link.is_approved ? "Approved" : "Rejected"}
              >
                {link.is_approved ? <Check className="size-3.5" /> : <X className="size-3.5" />}
              </Button>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <Card className="relative w-full max-w-full min-w-0 overflow-hidden">
      <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border/70 p-4 sm:p-5 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-xl bg-linear-to-br from-brand-600 to-emerald-600 text-white shadow-sm shadow-brand-700/20 shrink-0">
            <Sparkles className="size-4" />
          </div>
          <div>
            <CardTitle className="text-sm sm:text-base">Topic Alignment</CardTitle>
            <p className="text-[11px] sm:text-xs text-muted-foreground">
              {horizontalLinks.length} Horizontal (same class) • {verticalLinks.length} Vertical (across years) •{" "}
              {approvedCount} Approved
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
          {onSuggestClinical && (
            <Button
              variant="soft"
              size="xs"
              className="sm:h-8 sm:px-3 sm:text-xs"
              onClick={handleSuggestClinicalClick}
              disabled={isSuggesting || isLoading}
            >
              <Sparkles className="size-3.5" />
              <span>{isSuggesting ? "Adding..." : "Suggest Clinical"}</span>
            </Button>
          )}

          <Button
            variant="outline"
            size="xs"
            className="sm:h-8 sm:px-3 sm:text-xs"
            onClick={() => setShowAddForm(true)}
            disabled={isLoading}
          >
            <Plus className="size-3.5" />
            <span>New Link</span>
          </Button>

          <Button
            variant="outline"
            size="xs"
            className="sm:h-8 sm:px-3 sm:text-xs"
            onClick={() => onBulkApprove(true)}
            disabled={isLoading}
          >
            <CheckCheck className="size-3.5" />
            <span>All</span>
          </Button>

          <Button
            variant="ghost"
            size="xs"
            className="sm:h-8 sm:px-3 sm:text-xs"
            onClick={() => onBulkApprove(false)}
            disabled={isLoading}
          >
            <RotateCcw className="size-3.5" />
            <span>Clear</span>
          </Button>

          <Button
            data-tour="generate"
            variant="brand"
            size="lg"
            className="w-full sm:w-auto mt-1 sm:mt-0 min-w-[190px]"
            onClick={onProceed}
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <RefreshCw className="size-4 animate-spin" />
                <span>Generating Timetable...</span>
              </>
            ) : (
              <>
                <span>Build Timetable ({approvedCount})</span>
                <ArrowRight className="size-3.5" />
              </>
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="p-4 sm:p-5 pt-4 space-y-3">
        {suggestMessage && (
          <div className="flex items-center justify-between rounded-lg border border-purple-200 bg-purple-50/70 px-3 py-2 text-xs text-purple-900 dark:border-purple-800 dark:bg-purple-950/40 dark:text-purple-200">
            <span>{suggestMessage}</span>
            <Button variant="ghost" size="icon-sm" onClick={() => setSuggestMessage(null)}>
              <X className="size-3.5" />
            </Button>
          </div>
        )}

        <Tabs defaultValue="all">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <TabsList className="w-full sm:w-fit grid grid-cols-3 sm:inline-flex">
              <TabsTrigger value="all">All ({visibleLinks.length})</TabsTrigger>
              <TabsTrigger value="horizontal">
                <GitMerge className="size-3 text-sky-600 hidden xs:inline" />
                <span>Horiz ({horizontalLinks.length})</span>
              </TabsTrigger>
              <TabsTrigger value="vertical">
                <Link2 className="size-3 text-purple-600 hidden xs:inline" />
                <span>Vert ({verticalLinks.length})</span>
              </TabsTrigger>
            </TabsList>
            {isMultiCohort && (
              <Select
                aria-label="Filter links by class"
                value={cohortFilter}
                onChange={(e) => setCohortFilter(e.target.value)}
                className="h-8 w-full text-xs sm:w-48"
              >
                <option value="ALL">All classes ({cohortKeys.length})</option>
                {cohortKeys.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            )}
          </div>

          <TabsContent value="all" className="pt-2">
            {renderLinkList(visibleLinks, "HORIZONTAL")}
          </TabsContent>
          <TabsContent value="horizontal" className="pt-2">
            {renderLinkList(horizontalLinks, "HORIZONTAL")}
          </TabsContent>
          <TabsContent value="vertical" className="pt-2">
            {renderLinkList(verticalLinks, "VERTICAL")}
          </TabsContent>
        </Tabs>
      </CardContent>

      {/* Dialog for Adding Custom Link */}
      <Dialog open={showAddForm} onOpenChange={setShowAddForm}>
        <DialogContent onClose={() => setShowAddForm(false)}>
          <DialogHeader>
            <DialogTitle>New Topic Link</DialogTitle>
            <DialogDescription>
              Linked topics in the same class are taught in the same week, in logical order.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-1">
            <div className="space-y-1.5">
              <Label>Source Topic</Label>
              <Select value={srcIdx} onChange={(e) => setSrcIdx(Number(e.target.value))}>
                {topics.map((t, idx) => (
                  <option key={idx} value={idx}>
                    {t.cohort ? `${t.cohort} · ` : ""}[{t.discipline}] {t.topic_title.slice(0, 55)}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Target Topic</Label>
              <Select value={tgtIdx} onChange={(e) => setTgtIdx(Number(e.target.value))}>
                {topics.map((t, idx) => (
                  <option key={idx} value={idx}>
                    {t.cohort ? `${t.cohort} · ` : ""}[{t.discipline}] {t.topic_title.slice(0, 55)}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select
                value={linkType}
                onChange={(e) => setLinkType(e.target.value as "HORIZONTAL" | "VERTICAL")}
              >
                <option value="HORIZONTAL">Horizontal (same class, different subjects)</option>
                <option value="VERTICAL">Vertical (same topic, another year)</option>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Note (Optional)</Label>
              <Input
                value={customRationale}
                onChange={(e) => setCustomRationale(e.target.value)}
                placeholder="Reason for linking..."
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowAddForm(false)}>
                Cancel
              </Button>
              <Button
                variant="brand"
                onClick={handleCreateCustomLink}
                disabled={srcIdx === tgtIdx}
              >
                Create Link
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
};
