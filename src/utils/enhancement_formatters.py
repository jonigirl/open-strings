from __future__ import annotations

import xml.etree.ElementTree as ET


def _fmt(value, unit: str = "", decimals: int = 0) -> str:
    if value is None:
        return "?"
    try:
        v = float(value)
        if decimals:
            return f"{v:,.{decimals}f}{unit}"
        return f"{int(round(v)):,}{unit}"
    except (TypeError, ValueError):
        return str(value)


def _find(root: ET.Element, tag: str) -> ET.Element | None:
    return root.find(f".//{tag}")


def _attr(root: ET.Element, tag: str, attr: str, default=None):
    el = _find(root, tag)
    return el.get(attr, default) if el is not None else default


_OVERHEAT_PLACEHOLDER = 450_000


# Hook points that are supplied by scripts/generate_enhancements_ini.py.
# Lightweight defaults keep this module importable and test-safe.
def _mission_loc_key(root):
    return None


def _classify_mission_engagement(loc_key):
    return "Ship"


def _extract_mission_flags(root):
    return []


def _extract_difficulty(element):
    return ""


def _extract_mission_xp(root, reputation_lookup=None):
    return 0


def _extract_spawn_counts(element):
    return (0, 0, 0)


def _extract_turret_info(root):
    return None


def _fire_rate(root):
    return None


def _fire_modes(root, loc=None):
    return []


def _loadout_summary(root):
    return ("", "")


def _armor_stats_block(armor_root):
    return ""


def _poly_type(elem: ET.Element) -> str:
    return elem.get("__type") or elem.tag


def _find_by_type(root: ET.Element, type_name: str) -> ET.Element | None:
    for el in root.iter():
        if el.get("__type") == type_name or el.tag == type_name:
            return el
    return None


def _resource_amount(amount_el: ET.Element) -> str | None:
    unit = amount_el.find(".//SPowerSegmentResourceUnit")
    if unit is not None:
        return unit.get("units")
    std = amount_el.find(".//SStandardResourceUnit")
    if std is not None:
        return std.get("standardResourceUnits")
    micro = amount_el.find(".//SMicroResourceUnit")
    if micro is not None:
        return micro.get("microResourceUnits")
    return None


def _find_resource(root: ET.Element, resource: str) -> str | None:
    for delta_type in ("ItemResourceDeltaGeneration", "ItemResourceDeltaConversion", "ItemResourceDeltaConsumption"):
        for delta in root.iter(delta_type):
            for child in delta:
                if child.get("resource") == resource:
                    val = _resource_amount(child)
                    if val is not None:
                        return val
    return None


def enhancements_shield(root: ET.Element) -> str:
    el = _find(root, "SCItemShieldGeneratorParams")
    if el is None:
        return ""
    hp = el.get("MaxShieldHealth")
    regen = el.get("MaxShieldRegen")
    downed = el.get("DownedRegenDelay")
    damaged = el.get("DamagedRegenDelay")
    pwr = _find_resource(root, "Power")
    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")

    resist_entries = list(el.findall("ShieldResistance/SShieldResistance"))

    def _resist_pct(idx: int) -> str | None:
        if idx >= len(resist_entries):
            return None
        e = resist_entries[idx]
        try:
            mn = float(e.get("Min", "0")) * 100
            mx = float(e.get("Max", "0")) * 100
        except (TypeError, ValueError):
            return None
        if mn == 0 and mx == 0:
            return None
        lo, hi = (mn, mx) if mn <= mx else (mx, mn)
        return f"{lo:+.0f}% - {hi:+.0f}%"

    lines = []
    if hp is not None or regen is not None:
        lines.append(f"Max HP: {_fmt(hp)}  |  Regen: {_fmt(regen, ' HP/s')}")
    delays = []
    if downed is not None:
        delays.append(f"Downed Delay: {_fmt(downed, 's', 1)}")
    if damaged is not None:
        delays.append(f"Damaged Delay: {_fmt(damaged, 's', 1)}")
    if delays:
        lines.append("  |  ".join(delays))

    phys_resist = _resist_pct(0)
    energy_resist = _resist_pct(1)
    if phys_resist or energy_resist:
        parts = []
        if phys_resist:
            parts.append(f"Phys: {phys_resist}")
        if energy_resist:
            parts.append(f"Energy: {energy_resist}")
        lines.append("Resist:  " + "  |  ".join(parts))

    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))

    if pwr is not None:
        lines.append(f"Power Draw: {_fmt(pwr, ' PU/s')}")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")
    return "\\n".join(lines)


_DAMAGE_TYPES = (
    "DamagePhysical",
    "DamageEnergy",
    "DamageDistortion",
    "DamageThermal",
    "DamageBiochemical",
    "DamageStun",
)
_DAMAGE_LABELS = {
    "DamagePhysical": "Phys",
    "DamageEnergy": "Energy",
    "DamageDistortion": "Distort",
    "DamageThermal": "Thermal",
    "DamageBiochemical": "Bio",
    "DamageStun": "Stun",
}


def _ammo_damage_breakdown(ammo_root: ET.Element) -> tuple[float, dict]:
    totals: dict[str, float] = {}
    damage_elem = ammo_root.find(".//damage")
    if damage_elem is not None:
        for info in damage_elem.iter("DamageInfo"):
            for attr in _DAMAGE_TYPES:
                try:
                    v = float(info.get(attr, 0))
                    if v:
                        lbl = _DAMAGE_LABELS[attr]
                        totals[lbl] = totals.get(lbl, 0.0) + v
                except ValueError:
                    pass
    else:
        for info in ammo_root.iter("DamageInfo"):
            parent_tags = set()
            node = info
            while node is not None:
                parent_tags.add(node.tag)
                node = None
            for attr in _DAMAGE_TYPES:
                try:
                    v = float(info.get(attr, 0))
                    if v:
                        lbl = _DAMAGE_LABELS[attr]
                        totals[lbl] = totals.get(lbl, 0.0) + v
                except ValueError:
                    pass
            break
    return sum(totals.values()), totals


def enhancements_missile(root: ET.Element) -> str:
    lines = []

    try:
        for el in root.iter():
            try:
                if "missile" in el.tag.lower() or "projectile" in el.tag.lower():
                    velocity = el.get("speed") or el.get("velocity") or el.get("initialVelocity")
                    if velocity and velocity != "0":
                        try:
                            vel_val = float(velocity)
                            if vel_val > 0:
                                lines.append(f"Velocity: {vel_val:,.0f} m/s")
                        except (ValueError, TypeError):
                            pass

                    lifetime = el.get("lifetime") or el.get("maxLifetime") or el.get("burnTime")
                    if lifetime and lifetime != "0":
                        try:
                            life_val = float(lifetime)
                            if life_val > 0:
                                lines.append(f"Lifetime: {life_val:.2f}s")
                        except (ValueError, TypeError):
                            pass

                if "guidance" in el.tag.lower() or "tracking" in el.tag.lower():
                    guidance_type = (
                        el.get("guidanceType")
                        or el.get("type")
                        or el.tag.replace("Guidance", "").replace("Tracking", "")
                    )
                    if guidance_type and "none" not in guidance_type.lower():
                        lines.append(f"Guidance: {guidance_type}")

                    seeker_type = el.get("seekerType") or el.get("seekerMode")
                    if seeker_type and "none" not in seeker_type.lower():
                        lines.append(f"Seeker: {seeker_type}")

                    lock_time = el.get("lockTime") or el.get("lockOnTime") or el.get("lockAcquisitionTime")
                    if lock_time and lock_time != "0":
                        try:
                            time_val = float(lock_time)
                            if time_val > 0:
                                lines.append(f"Lock Time: {time_val:.2f}s")
                        except (ValueError, TypeError):
                            pass

                    min_lock = el.get("minLockRange") or el.get("minimumLockRange")
                    if min_lock and min_lock != "0":
                        try:
                            min_val = float(min_lock) / 1000
                            if min_val > 0:
                                lines.append(f"Min Lock Range: {min_val:,.1f} km")
                        except (ValueError, TypeError):
                            pass

                    max_lock = el.get("maxLockRange") or el.get("lockOnRange") or el.get("launchRange")
                    if max_lock and max_lock != "0":
                        try:
                            max_val = float(max_lock) / 1000
                            if max_val > 0:
                                lines.append(f"Max Lock Range: {max_val:,.1f} km")
                        except (ValueError, TypeError):
                            pass

                    track_range = el.get("trackingRange") or el.get("engagementRange") or el.get("maxEngagementRange")
                    if track_range and track_range != "0":
                        try:
                            track_val = float(track_range) / 1000
                            if track_val > 0:
                                lines.append(f"Tracking Range: {track_val:,.1f} km")
                        except (ValueError, TypeError):
                            pass

                    prox_range = el.get("proximityFuseRange") or el.get("detonationRange") or el.get("fuseRange")
                    if prox_range and prox_range != "0":
                        try:
                            prox_val = float(prox_range)
                            if prox_val > 0:
                                lines.append(f"Proximity Range: {prox_val:,.0f} m")
                        except (ValueError, TypeError):
                            pass

                    max_g = el.get("maxGForce") or el.get("maxAcceleration") or el.get("maxG")
                    if max_g and max_g != "0":
                        try:
                            g_val = float(max_g)
                            if g_val > 0:
                                lines.append(f"Max G-Force: {g_val:.1f}G")
                        except (ValueError, TypeError):
                            pass

                    turn_rate = el.get("turnRate") or el.get("maxTurnRate") or el.get("angularVelocity")
                    if turn_rate and turn_rate != "0":
                        try:
                            turn_val = float(turn_rate)
                            if turn_val > 0:
                                lines.append(f"Turn Rate: {turn_val:.1f} deg/s")
                        except (ValueError, TypeError):
                            pass

                    detonation = el.get("detonationMode") or el.get("fuseMode") or el.get("detonationType")
                    if detonation and "none" not in detonation.lower():
                        lines.append(f"Detonation: {detonation}")

                if "propulsion" in el.tag.lower() or "thruster" in el.tag.lower() or "engine" in el.tag.lower():
                    accel = el.get("acceleration") or el.get("maxAcceleration") or el.get("thrust")
                    if accel and accel != "0":
                        try:
                            accel_val = float(accel)
                            if accel_val > 0:
                                lines.append(f"Acceleration: {accel_val:,.1f} m/s^2")
                        except (ValueError, TypeError):
                            pass

                if "propellant" in el.tag.lower() or "fuel" in el.tag.lower():
                    fuel_amount = el.get("amount") or el.get("fuelAmount")
                    if fuel_amount and fuel_amount != "0":
                        try:
                            fuel_val = float(fuel_amount)
                            if fuel_val > 0:
                                lines.append(f"Fuel: {fuel_val:.1f}s")
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass

        lock_min = _attr(root, "targetingParams", "lockRangeMin")
        lock_max = _attr(root, "targetingParams", "lockRangeMax")
        try:
            lmn = float(lock_min) if lock_min else None
        except (ValueError, TypeError):
            lmn = None
        try:
            lmx = float(lock_max) if lock_max else None
        except (ValueError, TypeError):
            lmx = None

        def _fmt_range_m(v: float) -> str:
            return f"{v / 1000:,.1f} km" if v >= 1000 else f"{v:,.0f} m"

        if lmn is not None and lmn > 0 and lmx is not None and lmx > 0:
            lines.append(f"Lock Range: {_fmt_range_m(lmn)} - {_fmt_range_m(lmx)}")
        elif lmn is not None and lmn > 0:
            lines.append(f"Min Lock Range: {_fmt_range_m(lmn)}")
        elif lmx is not None and lmx > 0:
            lines.append(f"Max Lock Range: {_fmt_range_m(lmx)}")

        arm_time = _attr(root, "SCItemMissileParams", "armTime")
        safety_dist = _attr(root, "SCItemMissileParams", "explosionSafetyDistance")
        cruise_speed = _attr(root, "GCSParams", "linearSpeed")

        try:
            arm_t = float(arm_time) if arm_time else None
        except (ValueError, TypeError):
            arm_t = None
        try:
            safety = float(safety_dist) if safety_dist else None
        except (ValueError, TypeError):
            safety = None
        try:
            speed = float(cruise_speed) if cruise_speed else None
        except (ValueError, TypeError):
            speed = None

        arm_parts = []
        if arm_t and arm_t > 0:
            arm_parts.append(f"Arm Time: {arm_t:.1f}s")
        if arm_t and arm_t > 0 and speed and speed > 0:
            arm_dist = arm_t * speed
            arm_parts.append(f"Arm Dist: {_fmt_range_m(arm_dist)}")
        if safety and safety > 0:
            arm_parts.append(f"Min Detonate: {safety:,.0f} m")
        if arm_parts:
            lines.append("  |  ".join(arm_parts))

        damage_info = _find(root, "DamageInfo")
        if damage_info is not None:
            total_dmg, breakdown = _ammo_damage_breakdown(root)
            if total_dmg and total_dmg > 0:
                type_str = ""
                if breakdown and len(breakdown) == 1:
                    type_str = f" ({list(breakdown.keys())[0]})"
                elif breakdown and len(breakdown) > 1:
                    type_str = " (" + " / ".join(f"{lbl}: {v:.1f}" for lbl, v in breakdown.items()) + ")"
                lines.append(f"Damage: {_fmt(total_dmg, '', 1)}{type_str}")

        blast = _attr(root, "ExplosionParams", "maxRadius")
        if not blast:
            blast = _attr(root, "ExplosionParams", "minRadius")
        if not blast:
            blast = _attr(root, "Warhead", "blastRadius")
        if not blast:
            blast = _attr(root, "DamageInfo", "DamageDropOffEnd")
        if blast:
            try:
                blast_val = float(blast)
                if blast_val > 0:
                    lines.append(f"Blast Radius: {blast_val:,.0f} m")
            except (ValueError, TypeError):
                pass

        eff_range = _attr(root, "ProjectileParams", "effectiveRange")
        if eff_range and eff_range != "0":
            try:
                eff_val = float(eff_range) / 1000
                if eff_val > 0:
                    lines.append(f"Effective Range: {eff_val:,.1f} km")
            except (ValueError, TypeError):
                pass

        em_sig = _attr(root, "EMSignature", "nominalSignature")
        if em_sig and em_sig != "0":
            try:
                em_val = float(em_sig)
                if em_val > 0:
                    lines.append(f"EM Signature: {em_val:,.0f}")
            except (ValueError, TypeError):
                pass

        ir_sig = _attr(root, "IRSignature", "nominalSignature")
        if ir_sig and ir_sig != "0":
            try:
                ir_val = float(ir_sig)
                if ir_val > 0:
                    lines.append(f"IR Signature: {ir_val:,.0f}")
            except (ValueError, TypeError):
                pass

        comp_hp = _attr(root, "SHealthComponentParams", "Health")
        if comp_hp is not None:
            lines.append(f"Component HP: {_fmt(comp_hp)}")
    except Exception:
        pass

    return "\\n".join(lines) if lines else ""


def enhancements_radar(root: ET.Element) -> str:
    lines = []

    for el in root.iter("aimAssist"):
        min_dist = el.get("distanceMinAssignment")
        max_dist = el.get("distanceMaxAssignment")
        try:
            min_v = float(min_dist) if min_dist else None
            max_v = float(max_dist) if max_dist else None
        except (TypeError, ValueError):
            min_v = max_v = None
        if min_v is not None and max_v is not None and max_v > 0:
            lines.append(f"Aim Assist Range: {min_v:,.0f}-{max_v:,.0f} m")
        break

    for el in root.iter("pingProperties"):
        cd = el.get("cooldownTime")
        if cd:
            try:
                cd_v = float(cd)
                lines.append(f"Ping Cooldown: {cd_v:.1f}s")
            except (TypeError, ValueError):
                pass
        break

    passive_capable = False
    active_capable = False
    for el in root.iter("SCItemRadarSignatureDetection"):
        if el.get("permitPassiveDetection") == "1":
            passive_capable = True
        if el.get("permitActiveDetection") == "1":
            active_capable = True

    modes = []
    if passive_capable:
        modes.append("Passive")
    if active_capable:
        modes.append("Active")
    if modes:
        lines.append(f"Detection Mode: {' / '.join(modes)}")

    pwr = _find_resource(root, "Power")
    if pwr is not None:
        lines.append(f"Power Draw: {_fmt(pwr, ' PU/s')}")

    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")

    return "\\n".join(lines) if lines else ""


def enhancements_mission(root: ET.Element, reputation_lookup: dict[str, int] | None = None) -> str:
    lines = []
    reputation_lookup = reputation_lookup or {}

    try:
        loc_key = _mission_loc_key(root)
        engagement = _classify_mission_engagement(loc_key)
        lines.append(f"<EM4>Engagement Type:</EM4> {engagement}")

        flags = _extract_mission_flags(root)
        lines.append(f"<EM4>Mission Type:</EM4> {', '.join(flags) if flags else 'Standard'}")

        difficulty = _extract_difficulty(root)
        if difficulty:
            lines.append(f"<EM4>Difficulty (1-7):</EM4> {difficulty}")

        total_rep_xp = _extract_mission_xp(root, reputation_lookup)
        if total_rep_xp > 0:
            lines.append(f"<EM4>Reputation XP:</EM4> +{total_rep_xp:,}")

        _, num_enemies, num_not_enemies = _extract_spawn_counts(root)
        if num_enemies > 0:
            lines.append(f"<EM4>Enemies:</EM4> {num_enemies}")
        if num_not_enemies > 0:
            lines.append(f"<EM4>Non-hostiles:</EM4> {num_not_enemies}")

        turret_info = _extract_turret_info(root)
        if turret_info:
            lines.append(f"<EM4>Turrets:</EM4> {turret_info}")

    except Exception:
        pass

    return "\\n".join(lines) if lines else ""


def enhancements_weapon(
    root: ET.Element,
    ammo_lookup: dict[str, ET.Element],
    loc: dict | None = None,
    magazine_lookup: dict[str, tuple[str, str]] | None = None,
) -> str:
    fr = _fire_rate(root)
    modes = _fire_modes(root, loc)
    pwr = _find_resource(root, "Power")

    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")
    overheat = _attr(root, "itemResourceParams", "overheatTemperature")

    weight = None
    for elem in root.iter():
        pt = _poly_type(elem)
        if "RigidPhysics" in pt or "StaticPhysics" in pt:
            mass_val = elem.get("Mass")
            if mass_val:
                try:
                    weight = float(mass_val)
                except ValueError:
                    pass
            break

    pellet_count = 1
    for elem in root.iter():
        if "SProjectileLauncher" in _poly_type(elem):
            try:
                pc = int(elem.get("pelletCount", "1"))
                if pc > 1:
                    pellet_count = pc
            except ValueError:
                pass
            break

    ammo_container = _find(root, "SAmmoContainerComponentParams")
    ammo_record_id = ammo_container.get("ammoParamsRecord") if ammo_container is not None else None
    capacity = None

    if not ammo_record_id or ammo_record_id == "00000000-0000-0000-0000-000000000000":
        if magazine_lookup:
            for elem in root.iter():
                port_name = elem.get("itemPortName", "")
                entity_class = elem.get("entityClassName", "")
                if "magazine" in port_name.lower() and entity_class:
                    mag_info = magazine_lookup.get(entity_class)
                    if mag_info:
                        ammo_record_id, mag_capacity = mag_info
                        if mag_capacity:
                            capacity = mag_capacity
                    break

    total_dmg = breakdown = proj_speed = proj_lifetime = None
    dps = None
    ammo_root = None
    dmg_drop_min_dist = dmg_drop_per_m = dmg_drop_min = None
    if ammo_record_id and ammo_record_id != "00000000-0000-0000-0000-000000000000":
        ammo_root = ammo_lookup.get(ammo_record_id)
        if ammo_root is not None:
            total_dmg, breakdown = _ammo_damage_breakdown(ammo_root)
            if pellet_count > 1 and total_dmg:
                total_dmg *= pellet_count
                breakdown = {k: v * pellet_count for k, v in breakdown.items()}
            proj_speed = (
                ammo_root.get("speed")
                or ammo_root.get("velocity")
                or ammo_root.get("projectileSpeed")
                or ammo_root.get("initialSpeed")
            )
            proj_lifetime = (
                ammo_root.get("lifetime") or ammo_root.get("projectileLifetime") or ammo_root.get("maxLifetime")
            )
            if total_dmg and fr:
                try:
                    dps = total_dmg * float(fr) / 60.0
                except ValueError:
                    pass

            for elem in ammo_root.iter():
                tag = elem.tag
                if tag == "damageDropMinDistance":
                    for d in elem:
                        if _poly_type(d) == "DamageInfo" or "DamageInfo" in d.tag:
                            try:
                                dmg_drop_min_dist = float(d.get("DamagePhysical", 0)) + float(d.get("DamageEnergy", 0))
                            except ValueError:
                                pass
                elif tag == "damageDropPerMeter":
                    for d in elem:
                        if _poly_type(d) == "DamageInfo" or "DamageInfo" in d.tag:
                            try:
                                dmg_drop_per_m = float(d.get("DamagePhysical", 0)) + float(d.get("DamageEnergy", 0))
                            except ValueError:
                                pass
                elif tag == "damageDropMinDamage":
                    for d in elem:
                        if _poly_type(d) == "DamageInfo" or "DamageInfo" in d.tag:
                            try:
                                dmg_drop_min = float(d.get("DamagePhysical", 0)) + float(d.get("DamageEnergy", 0))
                            except ValueError:
                                pass

    regen = _find(root, "SWeaponRegenConsumerParams")
    regen_rate = regen_cooldown = regen_cost = None
    if regen is not None:
        if not capacity:
            capacity = regen.get("maxAmmoLoad")
        regen_rate = regen.get("requestedRegenPerSec")
        regen_cooldown = regen.get("regenerationCooldown")
        regen_cost = regen.get("regenerationCostPerBullet")
    elif ammo_container is not None and not capacity:
        capacity = ammo_container.get("maxAmmoCount")

    lines = []
    if weight is not None and weight > 0:
        lines.append(f"Weight: {weight:.1f} kg")
    if fr:
        lines.append(f"Fire Rate: {_fmt(fr, ' RPM')}")
    if modes:
        lines.append(f"Fire Modes: {' / '.join(modes)}")

    if total_dmg is not None and total_dmg > 0:
        type_str = ""
        if breakdown and len(breakdown) == 1:
            type_str = f" ({list(breakdown.keys())[0]})"
        elif breakdown and len(breakdown) > 1:
            type_str = " (" + " / ".join(f"{lbl}: {v:.1f}" for lbl, v in breakdown.items()) + ")"
        pellet_str = f" x{pellet_count}" if pellet_count > 1 else ""
        dmg_part = f"Alpha Dmg: {_fmt(total_dmg, '', 1)}{pellet_str}{type_str}"
        dps_part = f"DPS: {_fmt(dps, '', 1)}" if dps else ""
        lines.append("  |  ".join(p for p in [dmg_part, dps_part] if p))

    if capacity:
        lines.append(f"Ammo: {_fmt(capacity)}")
    if regen_rate or regen_cooldown:
        parts = []
        if regen_rate:
            parts.append(f"Regen: {_fmt(regen_rate)}/s")
        if regen_cooldown:
            parts.append(f"Cooldown: {_fmt(regen_cooldown, 's', 1)}")
        if regen_cost:
            parts.append(f"Cost/Shot: {_fmt(regen_cost)}")
        lines.append("  |  ".join(parts))
    if proj_speed is not None:
        try:
            speed_f = float(proj_speed)
            lifetime_f = float(proj_lifetime)
            rng_m = speed_f * lifetime_f
            range_label = "Absolute Range" if magazine_lookup is not None else "Range"
            if rng_m >= 1000:
                lines.append(f"Velocity: {_fmt(proj_speed, ' m/s')}  |  {range_label}: {rng_m / 1000:,.1f} km")
            else:
                lines.append(f"Velocity: {_fmt(proj_speed, ' m/s')}  |  {range_label}: {rng_m:,.0f} m")
        except (TypeError, ValueError):
            pass

    if dmg_drop_min_dist is not None and dmg_drop_min_dist > 0:
        drop_parts = [f"Full Dmg to: {dmg_drop_min_dist:.0f} m"]
        if dmg_drop_per_m is not None and dmg_drop_per_m > 0:
            drop_parts.append(f"Drop: -{dmg_drop_per_m:.2f}/m")
        if dmg_drop_min is not None and dmg_drop_min > 0:
            drop_parts.append(f"Min Dmg: {dmg_drop_min:.1f}")
        lines.append("  |  ".join(drop_parts))

    if pwr:
        lines.append(f"Power Draw: {_fmt(pwr, ' PU/s')}")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")
    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))
    if overheat is not None and magazine_lookup is None:
        try:
            if float(overheat) < _OVERHEAT_PLACEHOLDER:
                lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
        except (ValueError, TypeError):
            lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
    return "\\n".join(lines)


def enhancements_ship_dataforge(
    root: ET.Element,
    controller_root: ET.Element | None,
    loc: dict | None = None,
    armor_lookup: dict[str, ET.Element] | None = None,
) -> str:
    vpc = _find(root, "VehicleComponentParams")
    if vpc is None:
        return ""

    crew_size = vpc.get("crewSize")
    career_key = (vpc.get("vehicleCareer") or "").lstrip("@")
    role_key = (vpc.get("vehicleRole") or "").lstrip("@")
    career = (loc or {}).get(career_key) if career_key else None
    role = (loc or {}).get(role_key) if role_key else None

    bbox = vpc.find("maxBoundingBoxSize")
    length = bbox.get("y") if bbox is not None else None

    ins = _find(root, "shipInsuranceParams")
    ins_base = ins.get("baseWaitTimeMinutes") if ins is not None else None
    ins_express = ins.get("mandatoryWaitTimeMinutes") if ins is not None else None

    weapons_line, core_line = _loadout_summary(root)

    armor_block = ""
    if armor_lookup:
        for entry in root.iter("SItemPortLoadoutEntryParams"):
            if entry.get("itemPortName") in ("hardpoint_armor", "hardpoint_armour"):
                armor_class = (entry.get("entityClassName") or "").lower()
                if armor_class:
                    armor_root = armor_lookup.get(armor_class)
                    if armor_root is not None:
                        armor_block = _armor_stats_block(armor_root)
                break

    scm = max_spd = boost_fwd = boost_bwd = None
    pitch = roll = yaw = None
    if controller_root is not None:
        ifcs = _find(controller_root, "IFCSParams")
        if ifcs is not None:
            scm = ifcs.get("scmSpeed")
            max_spd = ifcs.get("maxSpeed")
            boost_fwd = ifcs.get("boostSpeedForward")
            boost_bwd = ifcs.get("boostSpeedBackward")
        sp = _find_by_type(controller_root, "SIFCSSpeedProfile")
        if sp is not None:
            av = sp.find("angularVelocity")
            if av is not None:
                pitch = av.get("x")
                roll = av.get("y")
                yaw = av.get("z")

    lines = []

    if scm is not None or max_spd is not None:
        lines.append(f"SCM: {_fmt(scm, ' m/s')}  |  Max: {_fmt(max_spd, ' m/s')}")
    if boost_fwd is not None or boost_bwd is not None:
        lines.append(f"Boost: +{_fmt(boost_fwd, ' m/s')}  /  -{_fmt(boost_bwd, ' m/s')}")
    if pitch is not None:
        lines.append(f"Pitch: {_fmt(pitch, 'deg/s')}  |  Roll: {_fmt(roll, 'deg/s')}  |  Yaw: {_fmt(yaw, 'deg/s')}")

    basics = []
    if crew_size is not None:
        basics.append(f"Crew: {_fmt(crew_size)}")
    if length is not None:
        basics.append(f"Length: {_fmt(length, 'm', 1)}")
    if career is not None:
        basics.append(f"Class: {career}")
    if role is not None:
        basics.append(f"Role: {role}")
    if basics:
        lines.append("  |  ".join(basics))

    if weapons_line:
        lines.append(weapons_line)
    if core_line:
        lines.append(core_line)
    if armor_block:
        lines.append(armor_block)

    if ins_base is not None:
        lines.append(f"Insurance: {_fmt(ins_base, ' min', 2)} base  |  {_fmt(ins_express, ' min', 2)} express")

    return "\\n".join(lines)


def enhancements_fps_attachment(root: ET.Element) -> str:
    wm = _find(root, "SWeaponModifierComponentParams")
    if wm is None:
        return ""

    ws = wm.find(".//weaponStats")
    if ws is None:
        return ""

    def _f(el: ET.Element | None, attr: str) -> float | None:
        if el is None:
            return None
        raw = el.get(attr)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _nz(v: float | None, default: float = 1.0) -> bool:
        return v is not None and abs(v - default) > 1e-6

    lines: list[str] = []

    mod_parts = []
    for attr, label in (
        ("damageMultiplier", "Damage"),
        ("fireRateMultiplier", "Fire Rate"),
        ("projectileSpeedMultiplier", "Projectile"),
        ("chargeTimeMultiplier", "Charge Time"),
        ("ammoCostMultiplier", "Ammo Cost"),
        ("heatGenerationMultiplier", "Heat"),
        ("soundRadiusMultiplier", "Sound"),
    ):
        v = _f(ws, attr)
        if _nz(v):
            mod_parts.append(f"{label}: x{v:.3g}")
    if mod_parts:
        lines.append("Weapon Mod: " + "  |  ".join(mod_parts))

    spread = ws.find("spreadModifier")
    if spread is not None:
        spread_parts = []
        for attr, label in (
            ("minMultiplier", "Min"),
            ("maxMultiplier", "Max"),
            ("firstAttackMultiplier", "First"),
            ("attackMultiplier", "Attack"),
            ("decayMultiplier", "Decay"),
        ):
            v = _f(spread, attr)
            if _nz(v):
                spread_parts.append(f"{label}: x{v:.3g}")
        additive = _f(spread, "additiveModifier")
        if additive is not None and abs(additive) > 1e-6:
            spread_parts.append(f"Add: {additive:+.3g}")
        if spread_parts:
            lines.append("Spread: " + "  |  ".join(spread_parts))

    aim = ws.find("aimModifier")
    if aim is not None:
        aim_parts = []
        zoom = _f(aim, "zoomScale")
        second_zoom = _f(aim, "secondZoomScale")
        zoom_time = _f(aim, "zoomTimeScale")
        if _nz(zoom):
            aim_parts.append(f"Zoom: x{zoom:.3g}")
        if _nz(second_zoom):
            aim_parts.append(f"Alt Zoom: x{second_zoom:.3g}")
        if _nz(zoom_time):
            aim_parts.append(f"ADS Time: x{zoom_time:.3g}")
        if aim_parts:
            lines.append("Aiming: " + "  |  ".join(aim_parts))

    recoil = ws.find("recoilModifier")
    if recoil is not None:
        recoil_parts = []
        for attr, label in (
            ("fireRecoilStrengthMultiplier", "Strength"),
            ("angleRecoilStrengthMultiplier", "Angle"),
            ("randomnessMultiplier", "Randomness"),
            ("decayMultiplier", "Decay"),
        ):
            v = _f(recoil, attr)
            if _nz(v):
                recoil_parts.append(f"{label}: x{v:.3g}")
        if recoil_parts:
            lines.append("Recoil: " + "  |  ".join(recoil_parts))

    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")

    return "\\n".join(lines)


def enhancements_ship_fuel(root: ET.Element) -> str:
    lines = []

    attach = _find(root, "AttachDef")
    if attach is not None:
        fuel_type = attach.get("Type")
        size = attach.get("Size")
        grade = attach.get("Grade")
        if fuel_type:
            lines.append(f"Type: {fuel_type}")
        if size or grade:
            parts = []
            if size:
                parts.append(f"Size: {size}")
            if grade:
                parts.append(f"Grade: {grade}")
            lines.append("  |  ".join(parts))

    intake = _find(root, "SCItemFuelIntakeParams")
    if intake is not None:
        push = intake.get("fuelPushRate")
        min_rate = intake.get("minimumRate")
        intake_parts = []
        if push is not None:
            intake_parts.append(f"Push Rate: {_fmt(push)}")
        if min_rate is not None:
            intake_parts.append(f"Min Rate: {_fmt(min_rate)}")
        if intake_parts:
            lines.append("Intake: " + "  |  ".join(intake_parts))

    tank = _find(root, "SCItemFuelTankParams")
    if tank is not None:
        h_flow = tank.get("hydrogenMaxFlowMultiplier")
        q_flow = tank.get("quantumMaxFlowMultiplier")
        flow_parts = []
        if h_flow is not None:
            flow_parts.append(f"Hydrogen Flow: x{_fmt(h_flow)}")
        if q_flow is not None:
            flow_parts.append(f"Quantum Flow: x{_fmt(q_flow)}")
        if flow_parts:
            lines.append("Flow Mult: " + "  |  ".join(flow_parts))

    fuel_cons = 0.0
    fuel_gen = 0.0
    for el in root.findall(
        ".//ItemResourceDeltaStorage/consumption[@resource='Fuel']/resourceAmountPerSecond/SStandardResourceUnit"
    ):
        try:
            fuel_cons += float(el.get("standardResourceUnits", "0"))
        except (TypeError, ValueError):
            pass
    for el in root.findall(
        ".//ItemResourceDeltaStorage/generation[@resource='Fuel']/resourceAmountPerSecond/SStandardResourceUnit"
    ):
        try:
            fuel_gen += float(el.get("standardResourceUnits", "0"))
        except (TypeError, ValueError):
            pass
    if fuel_gen > 0 or fuel_cons > 0:
        parts = []
        if fuel_gen > 0:
            parts.append(f"+{fuel_gen:,.3g}/s")
        if fuel_cons > 0:
            parts.append(f"-{fuel_cons:,.3g}/s")
        lines.append("Fuel Delta: " + "  |  ".join(parts))

    capacity = None
    for el in root.findall(".//ResourceContainer/capacity/*"):
        for attr in (
            "standardCargoUnits",
            "standardResourceUnits",
            "microSCU",
            "centiSCU",
            "units",
        ):
            raw = el.get(attr)
            if raw is None:
                continue
            try:
                capacity = float(raw)
                break
            except (TypeError, ValueError):
                continue
        if capacity is not None:
            break
    if capacity is not None:
        lines.append(f"Capacity: {capacity:,.3g}")

    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")

    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")
    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))

    return "\\n".join(lines)


def enhancements_countermeasure(root: ET.Element) -> str:
    lines = []

    attach = _find(root, "AttachDef")
    if attach is not None:
        size = attach.get("Size")
        grade = attach.get("Grade")
        if size or grade:
            parts = []
            if size:
                parts.append(f"Size: {size}")
            if grade:
                parts.append(f"Grade: {grade}")
            lines.append("  |  ".join(parts))

    ammo = _find(root, "SAmmoContainerComponentParams")
    if ammo is not None:
        ammo_parts = []
        initial = ammo.get("initialAmmoCount")
        maximum = ammo.get("maxAmmoCount")
        restock = ammo.get("maxRestockCount")
        if initial is not None:
            ammo_parts.append(f"Loaded: {_fmt(initial)}")
        if maximum is not None:
            ammo_parts.append(f"Capacity: {_fmt(maximum)}")
        if restock is not None:
            ammo_parts.append(f"Restocks: {_fmt(restock)}")
        if ammo_parts:
            lines.append("Ammo: " + "  |  ".join(ammo_parts))

    conn = _find(root, "connectionParams")
    if conn is not None:
        conn_parts = []
        cooldown = conn.get("powerActiveCooldown")
        heat_online = conn.get("heatRateOnline")
        max_glow = conn.get("maxGlow")
        if cooldown is not None:
            conn_parts.append(f"Cooldown: {_fmt(cooldown, 's', 1)}")
        if heat_online is not None:
            conn_parts.append(f"Heat Rate: {_fmt(heat_online)}")
        if max_glow is not None:
            conn_parts.append(f"Max Glow: {_fmt(max_glow)}")
        if conn_parts:
            lines.append("System: " + "  |  ".join(conn_parts))

    stats = _find(root, "overclockStats")
    if stats is not None:
        stat_parts = []
        for attr, label in (
            ("fireRateMultiplier", "Fire Rate"),
            ("heatGenerationMultiplier", "Heat"),
            ("soundRadiusMultiplier", "Sound"),
            ("chargeTimeMultiplier", "Charge"),
        ):
            raw = stats.get(attr)
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if abs(v - 1.0) > 1e-6:
                stat_parts.append(f"{label}: x{v:.3g}")
        if stat_parts:
            lines.append("Modifiers: " + "  |  ".join(stat_parts))

    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")

    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")
    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))

    return "\\n".join(lines)


def enhancements_lifesupport(root: ET.Element) -> str:
    lines = []

    life_gen = 0.0
    for el in root.findall(
        ".//ItemResourceDeltaConversion/generation[@resource='LifeSupport']/resourceAmountPerSecond/SStandardResourceUnit"
    ):
        try:
            life_gen += float(el.get("standardResourceUnits", "0"))
        except (TypeError, ValueError):
            pass
    if life_gen > 0:
        lines.append(f"Life Support Output: {life_gen:,.3g}/s")

    power_draw = 0.0
    for el in root.findall(
        ".//ItemResourceDeltaConversion/consumption[@resource='Power']/resourceAmountPerSecond/SPowerSegmentResourceUnit"
    ):
        try:
            power_draw += float(el.get("units", "0"))
        except (TypeError, ValueError):
            pass
    for el in root.findall(
        ".//ItemResourceDeltaConversion/consumption[@resource='Power']/resourceAmountPerSecond/SStandardResourceUnit"
    ):
        try:
            power_draw += float(el.get("standardResourceUnits", "0"))
        except (TypeError, ValueError):
            pass
    if power_draw > 0:
        lines.append(f"Power Draw: {power_draw:,.3g} PU/s")

    temp = _find(root, "itemResourceParams")
    if temp is not None:
        temp_parts = []
        for attr, label in (
            ("overheatTemperature", "Overheat"),
            ("overheatWarningTemperature", "Warning"),
            ("overheatRecoveryTemperature", "Recovery"),
            ("minCoolingTemperature", "Min Cooling"),
        ):
            val = temp.get(attr)
            if val is not None:
                temp_parts.append(f"{label}: {_fmt(val, 'K')}")
        if temp_parts:
            lines.append("Thermals: " + "  |  ".join(temp_parts))

    cooling = _find(root, "CoolingEqualizationRateAtTemperatureDifference")
    if cooling is not None:
        rate = cooling.get("coolingEqualizationRate")
        delta = cooling.get("temperatureDifference")
        if rate is not None or delta is not None:
            parts = []
            if rate is not None:
                parts.append(f"Rate: {_fmt(rate)}")
            if delta is not None:
                parts.append(f"Delta: {_fmt(delta, 'K')}")
            lines.append("Cooling: " + "  |  ".join(parts))

    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")
    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))

    distort = _attr(root, "SDistortionParams", "Maximum")
    if distort is not None:
        lines.append(f"Max Distortion: {_fmt(distort)}")

    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")

    return "\\n".join(lines)


def enhancements_cooler(root: ET.Element) -> str:
    cooling = _find_resource(root, "Coolant")
    pwr = _find_resource(root, "Power")
    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")
    overheat = _attr(root, "itemResourceParams", "overheatTemperature")

    lines = []
    if cooling is not None:
        lines.append(f"Cooling Rate: {_fmt(cooling, ' CR/s')}")
    if pwr is not None:
        lines.append(f"Power Draw: {_fmt(pwr, ' PU/s')}")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")
    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))
    if overheat is not None:
        try:
            if float(overheat) < _OVERHEAT_PLACEHOLDER:
                lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
        except (ValueError, TypeError):
            lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
    return "\\n".join(lines)


def enhancements_powerplant(root: ET.Element) -> str:
    gen = _find_resource(root, "Power")
    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")
    overheat = _attr(root, "itemResourceParams", "overheatTemperature")
    distort = _attr(root, "SDistortionParams", "Maximum")

    lines = []
    if gen is not None:
        lines.append(f"Power Output: {_fmt(gen, ' PU/s')}")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")
    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))
    if overheat is not None:
        try:
            if float(overheat) < _OVERHEAT_PLACEHOLDER:
                lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
        except (ValueError, TypeError):
            lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
    if distort is not None:
        lines.append(f"Max Distortion: {_fmt(distort)}")
    return "\\n".join(lines)


def enhancements_quantum_drive(root: ET.Element) -> str:
    qd = _find(root, "SCItemQuantumDriveParams")
    if qd is None:
        return ""
    fuel_req = qd.get("quantumFuelRequirement")

    params = _find_by_type(root, "SQuantumDriveParams")
    speed = params.get("driveSpeed") if params is not None else None
    spool = params.get("spoolUpTime") if params is not None else None
    cooldown = params.get("cooldownTime") if params is not None else None
    cal_rate = params.get("calibrationRate") if params is not None else None
    cal_min = params.get("minCalibrationRequirement") if params is not None else None
    cal_max = params.get("maxCalibrationRequirement") if params is not None else None
    accel1 = params.get("stageOneAccelRate") if params is not None else None
    accel2 = params.get("stageTwoAccelRate") if params is not None else None

    pwr = _find_resource(root, "Power")
    qt_fuel = _find_resource(root, "QuantumFuel")
    comp_hp = _attr(root, "SHealthComponentParams", "Health")
    em_sig = _attr(root, "EMSignature", "nominalSignature")
    ir_sig = _attr(root, "IRSignature", "nominalSignature")
    overheat = _attr(root, "itemResourceParams", "overheatTemperature")
    distort = _attr(root, "SDistortionParams", "Maximum")

    lines = []
    if speed is not None:
        speed_mm = float(speed) / 1_000_000
        spool_str = _fmt(spool, "s") if spool else "?"
        lines.append(f"QT Speed: {speed_mm:,.0f} Mm/s  |  Spool: {spool_str}")
    if cooldown is not None:
        lines.append(f"Cooldown: {_fmt(cooldown, 's', 1)}")
    if fuel_req is not None:
        lines.append(f"Fuel/Gm: {float(fuel_req):.4f}")
    if qt_fuel is not None:
        lines.append(f"QT Fuel Use: {_fmt(qt_fuel)} u/s")
    if accel1 is not None or accel2 is not None:
        parts = []
        if accel1:
            parts.append(f"S1: {_fmt(accel1)}")
        if accel2:
            parts.append(f"S2: {_fmt(accel2)}")
        lines.append("Accel:  " + "  |  ".join(parts))
    if cal_rate is not None:
        lines.append(f"Cal Rate: {_fmt(cal_rate)}  |  Required: {_fmt(cal_min)}-{_fmt(cal_max)}")
    if pwr is not None:
        lines.append(f"Power Draw: {_fmt(pwr, ' PU/s')}")
    if comp_hp is not None:
        lines.append(f"Component HP: {_fmt(comp_hp)}")
    if em_sig is not None or ir_sig is not None:
        parts = []
        if em_sig is not None:
            parts.append(f"EM: {_fmt(em_sig)}")
        if ir_sig is not None:
            parts.append(f"IR: {_fmt(ir_sig)}")
        lines.append("Signatures:  " + "  |  ".join(parts))
    if overheat is not None:
        try:
            if float(overheat) < _OVERHEAT_PLACEHOLDER:
                lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
        except (ValueError, TypeError):
            lines.append(f"Overheat Temp: {_fmt(overheat, 'K')}")
    if distort is not None:
        lines.append(f"Max Distortion: {_fmt(distort)}")
    return "\\n".join(lines)
