/** Shared mock data for the UI prototype examples. No real API calls. */

export const MOCK_VERSION = '0.8.0'
export const RELEASES_URL = 'https://github.com/crzykidd/partfolder3d/releases'

export type Role = 'admin' | 'editor' | 'viewer'

// ─── Items ────────────────────────────────────────────────────────────────────

export interface MockItem {
  id: string
  title: string
  creator: string
  tags: string[]
  files: number
  sizeKb: number
  favorited: boolean
  color: string
  accent: string
  badge?: 'new' | 'rendered' | 'printing' | 'rendering'
  printCount: number
}

export const MOCK_ITEMS: MockItem[] = [
  { id: '1',  title: 'Articulated Dragon',        creator: 'McGybeer',         tags: ['articulated','dragon','flexi','print-in-place'], files: 7,  sizeKb: 8400,  favorited: true,  color: '#e07b39', accent: '#FF9C5B', badge: 'rendered', printCount: 12 },
  { id: '2',  title: 'Gridfinity 2×2 Bins',       creator: 'Zack Freedman',    tags: ['gridfinity','storage','organizer'],               files: 4,  sizeKb: 1230,  favorited: true,  color: '#0FA4AB', accent: '#17C5CE', badge: 'new',      printCount: 3  },
  { id: '3',  title: '3DBenchy',                  creator: 'Creative Tools',   tags: ['benchmark','calibration','boat'],                 files: 2,  sizeKb: 580,   favorited: false, color: '#4A90D9', accent: '#6BAAEE', badge: undefined,  printCount: 47 },
  { id: '4',  title: 'Voronoi Lamp Shade',         creator: 'DesignMakeTech',   tags: ['lamp','voronoi','lighting','decor'],              files: 3,  sizeKb: 22800, favorited: true,  color: '#9B59B6', accent: '#BF7BE0', badge: 'rendered', printCount: 2  },
  { id: '5',  title: 'Cable Drop Clips',           creator: 'Various',          tags: ['cable-mgmt','utility','desk'],                    files: 2,  sizeKb: 320,   favorited: false, color: '#5D8AA8', accent: '#7FB3CC', badge: undefined,  printCount: 28 },
  { id: '6',  title: 'Tolerance Test Comb',        creator: 'Teaching Tech',    tags: ['calibration','tolerance','test','functional'],    files: 1,  sizeKb: 180,   favorited: false, color: '#27AE60', accent: '#46CC7E', badge: undefined,  printCount: 31 },
  { id: '7',  title: 'Skull Planter',              creator: 'Printables@FLOW',  tags: ['planter','skull','halloween','decor'],            files: 5,  sizeKb: 14200, favorited: true,  color: '#C0392B', accent: '#E74C3C', badge: 'rendered', printCount: 6  },
  { id: '8',  title: 'Phone Stand v3',             creator: 'Proper Printing',  tags: ['phone','stand','utility','bedside'],              files: 3,  sizeKb: 740,   favorited: false, color: '#E67E22', accent: '#F39C12', badge: 'new',      printCount: 19 },
  { id: '9',  title: 'MMU Filament Runout Sensor', creator: 'Prusa Research',   tags: ['mmu','prusa','sensor','functional'],              files: 8,  sizeKb: 2900,  favorited: true,  color: '#1ABC9C', accent: '#2ECC71', badge: undefined,  printCount: 1  },
  { id: '10', title: 'Voron 2.4 Toolhead',         creator: 'VoronDesign',      tags: ['voron','toolhead','3d-printer','mod'],            files: 23, sizeKb: 6800,  favorited: false, color: '#7D3C98', accent: '#A569BD', badge: 'rendering',printCount: 0  },
  { id: '11', title: 'D&D Dungeon Terrain Set',    creator: 'Printable Scenery',tags: ['terrain','tabletop','dnd','miniatures'],          files: 16, sizeKb: 31200, favorited: true,  color: '#795548', accent: '#A1887F', badge: 'rendered', printCount: 4  },
  { id: '12', title: 'Hex Wall Tiles (Magnetic)',  creator: 'ModiBot',          tags: ['wall-tile','hex','decor','magnetic'],             files: 6,  sizeKb: 4200,  favorited: false, color: '#388E3C', accent: '#66BB6A', badge: undefined,  printCount: 9  },
  { id: '13', title: 'Raspberry Pi 5 Case + Fan',  creator: 'Raspberry Stuff',  tags: ['raspberry-pi','case','cooling','sbc'],            files: 9,  sizeKb: 3600,  favorited: false, color: '#C62828', accent: '#EF5350', badge: 'new',      printCount: 7  },
  { id: '14', title: 'Articulated Octopus',        creator: 'Hho',              tags: ['articulated','flexi','octopus','cute'],           files: 3,  sizeKb: 5400,  favorited: true,  color: '#F06292', accent: '#FF80AB', badge: 'rendered', printCount: 14 },
  { id: '15', title: 'Wall Control Tool Holders',  creator: 'Space Efficient',  tags: ['tool-storage','wall-control','workshop'],         files: 11, sizeKb: 2800,  favorited: false, color: '#546E7A', accent: '#78909C', badge: undefined,  printCount: 22 },
  { id: '16', title: 'Cosplay Helmet v2 (Full)',   creator: 'Made In Metal 3D', tags: ['cosplay','helmet','wearable','iron-man'],         files: 31, sizeKb: 89000, favorited: true,  color: '#B71C1C', accent: '#EF5350', badge: 'printing', printCount: 1  },
]

// ─── Stats ────────────────────────────────────────────────────────────────────

export const MOCK_STATS = {
  total: 1842,
  printed: 637,
  favorites: 247,
  creators: 89,
  tags: 634,
  filamentKm: 4.7,
  filamentKg: 14.3,
  successRate: 91,
  jobsRunning: 3,
  pendingReviews: 5,
  imports: 12,
}

// ─── Tags ─────────────────────────────────────────────────────────────────────

export interface MockTag { label: string; count: number }

export const MOCK_TAG_CLOUD: MockTag[] = [
  { label: 'functional',    count: 284 },
  { label: 'organizer',     count: 231 },
  { label: 'articulated',   count: 178 },
  { label: 'miniatures',    count: 156 },
  { label: 'calibration',   count: 143 },
  { label: 'gridfinity',    count: 129 },
  { label: 'decor',         count: 118 },
  { label: 'mmu',           count: 97  },
  { label: 'terrain',       count: 91  },
  { label: 'cosplay',       count: 87  },
  { label: 'keychain',      count: 84  },
  { label: 'wearable',      count: 76  },
  { label: 'flexi',         count: 74  },
  { label: 'tool-storage',  count: 68  },
  { label: 'cable-mgmt',    count: 61  },
  { label: 'raspberry-pi',  count: 54  },
  { label: 'voron',         count: 49  },
  { label: 'benchmark',     count: 44  },
  { label: 'lamp',          count: 38  },
  { label: 'tabletop',      count: 33  },
]

// ─── Creators ─────────────────────────────────────────────────────────────────

export interface MockCreator { id: string; name: string; models: number; color: string }

export const MOCK_CREATORS: MockCreator[] = [
  { id: 'c1', name: 'Zack Freedman',      models: 143, color: '#0FA4AB' },
  { id: 'c2', name: 'McGybeer',           models: 89,  color: '#e07b39' },
  { id: 'c3', name: 'Teaching Tech',      models: 76,  color: '#27AE60' },
  { id: 'c4', name: 'Printable Scenery',  models: 68,  color: '#795548' },
  { id: 'c5', name: 'VoronDesign',        models: 54,  color: '#7D3C98' },
]

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export type JobStatus = 'running' | 'queued' | 'failed' | 'complete'

export interface MockJob {
  id: string
  name: string
  status: JobStatus
  progress?: number
  since: string
  target?: string
}

export const MOCK_JOBS: MockJob[] = [
  { id: 'j1', name: 'Render preview',        status: 'running',  progress: 67, since: '2m ago',  target: '"Articulated Dragon"'        },
  { id: 'j2', name: 'Tag inference',         status: 'running',  progress: 12, since: '5m ago',  target: '"Skull Planter"'             },
  { id: 'j3', name: 'Generate thumbnails',   status: 'running',  progress: 88, since: '8m ago',  target: '3 items'                     },
  { id: 'j4', name: 'Generate thumbnails',   status: 'queued',   since: '—',   target: '5 items'                                       },
  { id: 'j5', name: 'Orca slicer export',    status: 'failed',   since: '14m ago', target: '"Voron Toolhead"'                          },
  { id: 'j6', name: 'Import Thingiverse col',status: 'complete', since: '2h ago', target: '42 items'                                   },
  { id: 'j7', name: 'Backup to S3',          status: 'complete', since: '6h ago'                                                       },
]

export interface MockScheduledJob {
  id: string
  name: string
  schedule: string
  lastRun: string
  nextRun: string
  status: 'active' | 'paused'
}

export const MOCK_SCHEDULED_JOBS: MockScheduledJob[] = [
  { id: 's1', name: 'Nightly DB backup',     schedule: 'daily 2:00 am',   lastRun: '3h ago',    nextRun: 'in 21h',  status: 'active' },
  { id: 's2', name: 'Tag inference batch',   schedule: 'every 6h',        lastRun: '1h ago',    nextRun: 'in 5h',   status: 'active' },
  { id: 's3', name: 'Render queue worker',   schedule: 'every 15 min',    lastRun: '4m ago',    nextRun: 'in 11m',  status: 'active' },
  { id: 's4', name: 'Thingiverse sync',      schedule: 'weekly Sun 3:00', lastRun: '6 days ago',nextRun: 'in 22h',  status: 'paused' },
  { id: 's5', name: 'Export snapshot',       schedule: 'monthly 1st',     lastRun: '26 days ago',nextRun: 'in 4d',  status: 'active' },
]

// ─── Nav ──────────────────────────────────────────────────────────────────────

export interface NavItem {
  label: string
  icon: string
  badge?: number
}

export interface NavGroup {
  id: string
  label: string
  minRole: Role
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'library',
    label: 'Library',
    minRole: 'viewer',
    items: [
      { label: 'Catalog',   icon: 'grid'   },
      { label: 'Tags',      icon: 'tag'    },
      { label: 'Creators',  icon: 'users'  },
      { label: 'Favorites', icon: 'heart'  },
    ],
  },
  {
    id: 'import',
    label: 'Import',
    minRole: 'editor',
    items: [
      { label: 'Add Asset', icon: 'plus-circle' },
      { label: 'Inbox',     icon: 'inbox'       },
      { label: 'Imports',   icon: 'package'     },
    ],
  },
  {
    id: 'operations',
    label: 'Operations',
    minRole: 'admin',
    items: [
      { label: 'Jobs',            icon: 'cpu',            badge: 3 },
      { label: 'Scheduled Jobs',  icon: 'calendar'                 },
      { label: 'Issues',          icon: 'alert-triangle'           },
      { label: 'Change Log',      icon: 'git-branch'               },
      { label: 'Reviews',         icon: 'eye',            badge: 5 },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    minRole: 'admin',
    items: [
      { label: 'Users',             icon: 'user'     },
      { label: 'Invites',           icon: 'mail'     },
      { label: 'AI Providers',      icon: 'zap'      },
      { label: 'Site Capabilities', icon: 'settings' },
      { label: 'Backups',           icon: 'archive'  },
      { label: 'Export',            icon: 'download' },
      { label: 'Pending Tags',      icon: 'hash'     },
      { label: 'Settings',          icon: 'sliders'  },
    ],
  },
]

export function canSeeGroup(group: NavGroup, role: Role): boolean {
  if (group.minRole === 'viewer') return true
  if (group.minRole === 'editor') return role === 'editor' || role === 'admin'
  return role === 'admin'
}
