import type {
  CanonicalDimension,
  CanonicalMeasure,
  CanonicalUnit,
  ColumnSuggestion,
  ColumnType,
  PreviewBlock,
  PreviewPayload,
  QualityObservation,
  QualitySummary,
  SaveEditsPayload,
  SemanticRole,
  SupportedUnit
} from "./page_types";

const TARGET_UNIT_BY_MEASURE: Record<CanonicalMeasure, CanonicalUnit> = {
  yield: "kg/ha",
  moisture: "%",
  plant_height: "cm"
};

const SOURCE_UNIT_OPTIONS_BY_MEASURE: Record<CanonicalMeasure, SupportedUnit[]> = {
  yield: ["kg/ha", "t/ha"],
  moisture: ["%"],
  plant_height: ["cm", "m"]
};

export function normalizeUploadId(id: string | string[] | undefined): string | null {
  if (Array.isArray(id)) {
    return id[0] || null;
  }
  return id || null;
}

export function clonePreview(preview: PreviewPayload): PreviewPayload {
  return JSON.parse(JSON.stringify(preview)) as PreviewPayload;
}

export function effectiveType(column: ColumnSuggestion): ColumnType {
  return column.type_override ?? column.suggested;
}

export function countByRole(block: PreviewBlock): Record<SemanticRole, number> {
  return block.type_suggestions.reduce<Record<SemanticRole, number>>(
    (acc, column) => {
      acc[column.semantic_role] += 1;
      return acc;
    },
    {
      ignore: 0,
      date: 0,
      dimension: 0,
      measure: 0
    }
  );
}

export function blockWarningCount(block: PreviewBlock): number {
  return block.type_suggestions.filter((item) => item.warnings.length > 0).length;
}

export function extractEditPayload(preview: PreviewPayload | null): SaveEditsPayload {
  return {
    columns:
      preview?.blocks.flatMap((block) =>
        block.type_suggestions.map((item) => ({
          block_id: block.block_id,
          column: item.column,
          type_override: item.type_override,
          semantic_role: item.semantic_role,
          canonical_measure: item.canonical_measure,
          canonical_dimension: item.canonical_dimension,
          unit: item.unit
        }))
      ) || []
  };
}

export function stableEditPayload(preview: PreviewPayload | null): SaveEditsPayload {
  return {
    columns: extractEditPayload(preview).columns
      .map((item) => ({
        block_id: item.block_id,
        column: item.column,
        type_override: item.type_override ?? null,
        semantic_role: item.semantic_role,
        canonical_measure: item.canonical_measure ?? null,
        canonical_dimension: item.canonical_dimension ?? null,
        unit: item.unit ?? null
      }))
      .sort((left, right) => {
        const leftKey = `${left.block_id}::${left.column}`;
        const rightKey = `${right.block_id}::${right.column}`;
        return leftKey.localeCompare(rightKey);
      })
  };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function inferCanonicalMeasure(columnName: string): CanonicalMeasure | null {
  const normalized = columnName.toLowerCase();
  if (normalized.includes("yield") || normalized.includes("kg_ha") || normalized.includes("t_ha")) {
    return "yield";
  }
  if (normalized.includes("moisture") || normalized.includes("pct")) {
    return "moisture";
  }
  if (normalized.includes("height")) {
    return "plant_height";
  }
  return null;
}

export function inferDefaultUnit(columnName: string, measure: CanonicalMeasure | null): SupportedUnit | null {
  if (!measure) {
    return null;
  }

  const normalized = columnName.toLowerCase();
  if (measure === "yield") {
    if (normalized.includes("t_ha") || normalized.includes("t/ha")) {
      return "t/ha";
    }
    if (normalized.includes("kg_ha") || normalized.includes("kg/ha")) {
      return "kg/ha";
    }
  }
  if (measure === "moisture" && (normalized.includes("pct") || normalized.includes("%"))) {
    return "%";
  }
  if (measure === "plant_height") {
    if (normalized.includes("height_cm") || normalized.includes("_cm") || normalized.endsWith(" cm")) {
      return "cm";
    }
    if (normalized.includes("height_m") || normalized.includes("_m") || normalized.endsWith(" m")) {
      return "m";
    }
  }

  const supportedUnits = SOURCE_UNIT_OPTIONS_BY_MEASURE[measure];
  if (supportedUnits.length === 1) {
    return supportedUnits[0];
  }
  return null;
}

export function targetUnitForMeasure(measure: CanonicalMeasure | null): CanonicalUnit | null {
  return measure ? TARGET_UNIT_BY_MEASURE[measure] : null;
}

export function summarizeQuality(items: QualityObservation[]): QualitySummary {
  const summary: QualitySummary = {
    total: items.length,
    valid: 0,
    warning: 0,
    invalid: 0,
    flagged: 0
  };

  for (const item of items) {
    summary[item.validation_status] += 1;
    if ((item.quality_flags || []).length > 0) {
      summary.flagged += 1;
    }
  }

  return summary;
}

export function measureUnitOptions(measure: CanonicalMeasure | null): SupportedUnit[] {
  return measure ? SOURCE_UNIT_OPTIONS_BY_MEASURE[measure] : [];
}

export function inferCanonicalDimension(columnName: string): CanonicalDimension | null {
  const normalized = columnName.toLowerCase();
  if (normalized.includes("plot")) {
    return "plot_id";
  }
  if (normalized.includes("variety") || normalized.includes("cultivar") || normalized.includes("genotype")) {
    return "variety";
  }
  if (normalized.includes("treat") || normalized.includes("fert")) {
    return "treatment";
  }
  if (normalized.includes("location") || normalized.includes("site") || normalized.includes("field")) {
    return "location";
  }
  return null;
}

export function updateRoleDefaults(column: ColumnSuggestion, nextRole: SemanticRole): ColumnSuggestion {
  const next: ColumnSuggestion = {
    ...column,
    semantic_role: nextRole
  };

  if (nextRole === "measure") {
    next.type_override = effectiveType(column) === "numeric" ? column.type_override : "numeric";
    next.canonical_measure = column.canonical_measure || inferCanonicalMeasure(column.column);
    next.canonical_dimension = null;
    next.unit = column.unit || inferDefaultUnit(column.column, next.canonical_measure);
  } else if (nextRole === "dimension") {
    next.canonical_dimension = column.canonical_dimension || inferCanonicalDimension(column.column);
    next.canonical_measure = null;
    next.unit = null;
  } else if (nextRole === "date") {
    next.type_override = effectiveType(column) === "date" ? column.type_override : "date";
    next.canonical_measure = null;
    next.canonical_dimension = null;
    next.unit = null;
  } else {
    next.canonical_measure = null;
    next.canonical_dimension = null;
    next.unit = null;
  }

  return next;
}
