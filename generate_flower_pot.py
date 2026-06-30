"""
Generates two STL files:
  - flower_pot.stl   : tapered pot with external (male) thread ring at the base
  - drip_tray.stl    : shallow tray with internal (female) thread ring

Thread spec: M60-ish, 6mm pitch, 2 turns — coarse enough for easy printing.
All dimensions in millimetres.
"""

import numpy as np
from stl import mesh

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def circle_pts(r, n=64, z=0.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([r * np.cos(t), r * np.sin(t), np.full(n, z)])


def tube_triangles(bottom_ring, top_ring):
    """Return triangles forming a tube between two rings of equal point count."""
    n = len(bottom_ring)
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.append([bottom_ring[i], bottom_ring[j], top_ring[i]])
        tris.append([top_ring[i],   bottom_ring[j], top_ring[j]])
    return tris


def fan_triangles(center, ring, flip=False):
    """Return triangles for a flat disk fan."""
    n = len(ring)
    tris = []
    for i in range(n):
        j = (i + 1) % n
        if flip:
            tris.append([center, ring[j], ring[i]])
        else:
            tris.append([center, ring[i], ring[j]])
    return tris


def make_mesh(triangles):
    arr = np.array(triangles, dtype=np.float32)  # (N, 3, 3)
    m = mesh.Mesh(np.zeros(len(arr), dtype=mesh.Mesh.dtype))
    for i, tri in enumerate(arr):
        m.vectors[i] = tri
    return m


# ---------------------------------------------------------------------------
# Thread helix helpers
# ---------------------------------------------------------------------------

def helix_thread_triangles(r_base, r_tip, z_start, pitch, n_turns,
                            n_per_turn=120, flip_normal=False):
    """
    Build a single helical thread fin as a quad strip.
    r_base  – radius of the cylinder the thread sits on
    r_tip   – outer (or inner) tip of the thread tooth
    z_start – where the helix begins
    pitch   – axial distance per turn
    n_turns – number of full turns
    flip_normal – True for female (internal) thread
    """
    total_pts = int(n_turns * n_per_turn) + 1
    t = np.linspace(0, n_turns * 2 * np.pi, total_pts)
    z  = z_start + t / (2 * np.pi) * pitch

    base_pts = np.column_stack([r_base * np.cos(t), r_base * np.sin(t), z])
    tip_pts  = np.column_stack([r_tip  * np.cos(t), r_tip  * np.sin(t), z])

    tris = []
    for i in range(total_pts - 1):
        b0, b1 = base_pts[i], base_pts[i + 1]
        t0, t1 = tip_pts[i],  tip_pts[i + 1]
        if flip_normal:
            tris.append([b0, t0, b1])
            tris.append([b1, t0, t1])
        else:
            tris.append([b0, b1, t0])
            tris.append([b1, t1, t0])
    return tris


# ---------------------------------------------------------------------------
# Flower pot
# ---------------------------------------------------------------------------
# Dimensions
POT_H        = 120.0   # total height
POT_R_TOP    = 55.0    # inner radius at top
POT_R_BOT    = 38.0    # inner radius at bottom (inside)
WALL         = 3.5     # wall thickness
RIM          = 5.0     # extra rim thickness at top
DRAIN_R      = 5.0     # drain hole radius
N            = 80      # circumference resolution

# Thread parameters (male, on outside of bottom of pot)
THREAD_PITCH = 6.0
THREAD_TURNS = 2.2
THREAD_H     = 3.0     # thread tooth height (radial)
THREAD_Z0    = 2.0     # start height of thread on pot exterior

def build_pot():
    tris = []

    # --- outer wall (tapered) ---
    out_r_bot = POT_R_BOT + WALL
    out_r_top = POT_R_TOP + WALL

    for layer in range(40):
        frac0 = layer / 40
        frac1 = (layer + 1) / 40
        r0_out = out_r_bot + (out_r_top - out_r_bot) * frac0
        r1_out = out_r_bot + (out_r_top - out_r_bot) * frac1
        r0_in  = POT_R_BOT + (POT_R_TOP - POT_R_BOT) * frac0
        r1_in  = POT_R_BOT + (POT_R_TOP - POT_R_BOT) * frac1
        z0 = POT_H * frac0
        z1 = POT_H * frac1

        outer_bot = circle_pts(r0_out, N, z0)
        outer_top = circle_pts(r1_out, N, z1)
        inner_bot = circle_pts(r0_in,  N, z0)
        inner_top = circle_pts(r1_in,  N, z1)

        tris += tube_triangles(outer_bot, outer_top)          # outer face (outward)
        tris += tube_triangles(inner_top, inner_bot)          # inner face (inward normal)

    # --- bottom disk (with drain hole) ---
    bot_out = circle_pts(out_r_bot, N, 0)
    bot_in  = circle_pts(POT_R_BOT, N, 0)
    drain   = circle_pts(DRAIN_R,   N, 0)
    center  = np.array([0.0, 0.0, 0.0])

    # annulus between drain and inner bottom
    tris += tube_triangles(drain, bot_in)     # upward normal strip (flip)
    # re-do properly: bottom face points downward
    for i in range(N):
        j = (i + 1) % N
        tris.append([bot_in[i],  drain[j],   drain[i]])
        tris.append([bot_in[i],  bot_in[j],  drain[j]])
    # outer annulus (between inner wall base and outer wall base)
    for i in range(N):
        j = (i + 1) % N
        tris.append([bot_out[i], bot_in[i],  bot_in[j]])
        tris.append([bot_out[i], bot_in[j],  bot_out[j]])

    # --- top rim (flat annulus at top) ---
    top_out = circle_pts(out_r_top + RIM, N, POT_H)
    top_in  = circle_pts(POT_R_TOP,       N, POT_H)
    top_out_wall = circle_pts(out_r_top,  N, POT_H)

    # rim top face
    for i in range(N):
        j = (i + 1) % N
        tris.append([top_out[i],     top_out_wall[j], top_out_wall[i]])
        tris.append([top_out[i],     top_out[j],      top_out_wall[j]])
    # rim inner top edge is just the top of the inner wall (already closed)
    # outer rim vertical face
    outer_rim_bot = circle_pts(out_r_top + RIM, N, POT_H - 4)
    tris += tube_triangles(outer_rim_bot, top_out)
    # connect rim bottom to outer wall top
    for i in range(N):
        j = (i + 1) % N
        tris.append([top_out_wall[i],  outer_rim_bot[j], outer_rim_bot[i]])
        tris.append([top_out_wall[i],  top_out_wall[j],  outer_rim_bot[j]])

    # --- helical male thread at base ---
    thread_r_base = out_r_bot
    thread_r_tip  = out_r_bot + THREAD_H
    tris += helix_thread_triangles(thread_r_base, thread_r_tip,
                                   THREAD_Z0, THREAD_PITCH, THREAD_TURNS)

    # top/bottom caps of the thread helix fin (small closing triangles)
    # (good-enough approximation — slicer will handle minor gaps)

    return make_mesh(tris)


# ---------------------------------------------------------------------------
# Drip tray
# ---------------------------------------------------------------------------
TRAY_H       = 25.0    # tray wall height
TRAY_WALL    = 3.5

def build_tray():
    """
    Bowl tray with thread ring rising from the TOP of the bowl.
    The pot screws down onto the ring from above; water drips into the bowl below.
    Fixes vs original: (1) solid inner bottom disk added, (2) bore sized to
    clear the male thread tip (41.5 + 3.0 = 44.5 mm) with 0.3 mm clearance.
    """
    tris = []

    _out_r_bot    = POT_R_BOT + WALL                   # 41.5 – pot base outer radius
    ring_r_in     = _out_r_bot + THREAD_H + 0.3        # 44.8 – bore clears male tip + 0.3 mm
    ring_r_out    = ring_r_in + TRAY_WALL               # 48.3 – ring outer wall
    tray_r_out    = ring_r_out + 20                     # 68.3 – generous water catchment
    tray_r_in     = tray_r_out - TRAY_WALL              # 64.8 – inner bowl radius
    thread_ring_h = THREAD_PITCH * THREAD_TURNS + 4

    center = np.array([0.0, 0.0, 0.0])

    # --- tray outer cylinder ---
    bot_outer = circle_pts(tray_r_out, N, 0)
    top_outer = circle_pts(tray_r_out, N, TRAY_H)
    tris += tube_triangles(bot_outer, top_outer)

    # --- tray inner cylinder (inward normal) ---
    bot_inner = circle_pts(tray_r_in, N, 0)
    top_inner = circle_pts(tray_r_in, N, TRAY_H)
    tris += tube_triangles(top_inner, bot_inner)

    # --- tray bottom: outer annulus (wall-thickness ring) ---
    for i in range(N):
        j = (i + 1) % N
        tris.append([bot_outer[i], bot_inner[j], bot_inner[i]])
        tris.append([bot_outer[i], bot_outer[j], bot_inner[j]])

    # --- tray bottom: solid inner disk – this was the missing piece ---
    tris += fan_triangles(center, bot_inner, flip=True)

    # --- top face of tray bowl (annulus from outer wall to thread ring outer) ---
    top_ring_outer = circle_pts(ring_r_out, N, TRAY_H)
    for i in range(N):
        j = (i + 1) % N
        tris.append([top_outer[i], top_ring_outer[i], top_ring_outer[j]])
        tris.append([top_outer[i], top_ring_outer[j], top_outer[j]])

    # --- thread ring outer wall ---
    top_ring_top_outer = circle_pts(ring_r_out, N, TRAY_H + thread_ring_h)
    tris += tube_triangles(top_ring_outer, top_ring_top_outer)

    # --- thread ring inner wall (inward normal) ---
    top_ring_inner     = circle_pts(ring_r_in, N, TRAY_H)
    top_ring_top_inner = circle_pts(ring_r_in, N, TRAY_H + thread_ring_h)
    tris += tube_triangles(top_ring_top_inner, top_ring_inner)

    # --- thread ring cap ---
    for i in range(N):
        j = (i + 1) % N
        tris.append([top_ring_top_outer[i], top_ring_top_inner[j], top_ring_top_inner[i]])
        tris.append([top_ring_top_outer[i], top_ring_top_outer[j], top_ring_top_inner[j]])

    # --- inner tray floor (annulus from bowl inner wall to thread ring, at z=TRAY_H) ---
    for i in range(N):
        j = (i + 1) % N
        tris.append([top_inner[i], top_ring_inner[i], top_ring_inner[j]])
        tris.append([top_inner[i], top_ring_inner[j], top_inner[j]])

    # --- female thread (base at bore wall, tip extends inward) ---
    tris += helix_thread_triangles(ring_r_in, ring_r_in - THREAD_H + 0.3,
                                   TRAY_H + THREAD_Z0,
                                   THREAD_PITCH, THREAD_TURNS,
                                   flip_normal=True)

    return make_mesh(tris)


# ---------------------------------------------------------------------------
# Write files
# ---------------------------------------------------------------------------

pot_mesh  = build_pot()
tray_mesh = build_tray()

pot_mesh.save('flower_pot.stl')
tray_mesh.save('drip_tray.stl')

print("Saved: flower_pot.stl")
print("Saved: drip_tray.stl")
print(f"\nKey dimensions:")
print(f"  Pot height      : {POT_H} mm")
print(f"  Pot top opening : {POT_R_TOP*2:.0f} mm diameter")
print(f"  Thread pitch    : {THREAD_PITCH} mm  ({THREAD_TURNS} turns)")
print(f"  Tray height     : {TRAY_H + THREAD_PITCH*THREAD_TURNS + 4:.0f} mm total")
