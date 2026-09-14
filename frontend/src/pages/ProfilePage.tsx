import React, { useState, useEffect, useRef } from "react";
import { NavPath } from "../components/Sidebar";
import { UserProfile } from "../types";
import {
  getUserProfile,
  updateUserProfile,
  uploadProfilePhoto,
  deleteProfilePhoto,
  DEFAULT_USER_PROFILE,
} from "../services/api";
import {
  User,
  Shield,
  Award,
  Phone,
  Mail,
  MapPin,
  Building,
  Key,
  Camera,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Save,
  Loader2,
  Lock,
} from "lucide-react";

interface ProfilePageProps {
  onNavigate: (path: NavPath) => void;
  onProfileUpdated?: (updated: UserProfile) => void;
}

const ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"];
const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5MB

export function ProfilePage({ onNavigate, onProfileUpdated }: ProfilePageProps) {
  const [profile, setProfile] = useState<UserProfile>(DEFAULT_USER_PROFILE);
  const [formData, setFormData] = useState<UserProfile>(DEFAULT_USER_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getUserProfile().then((data) => {
      setProfile(data);
      setFormData(data);
      setLoading(false);
    });
  }, []);

  const handleInputChange = (field: keyof UserProfile, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
    setSuccessMessage(null);
    setErrorMessage(null);
  };

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setPhotoError(null);
    setSuccessMessage(null);

    // 1. Validate extension
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) {
      setPhotoError("Invalid file type. Please select a JPG, PNG, or WEBP image.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    // 2. Validate file size
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setPhotoError("File size exceeds 5 MB limit. Please select a smaller image.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setUploadingPhoto(true);
    try {
      const updated = await uploadProfilePhoto(file);
      setProfile(updated);
      setFormData(updated);
      if (onProfileUpdated) onProfileUpdated(updated);
      setSuccessMessage("Profile photo updated successfully");
      setTimeout(() => setSuccessMessage(null), 3500);
    } catch (err: any) {
      setPhotoError(err.message || "Photo upload failed");
    } finally {
      setUploadingPhoto(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handlePhotoRemove = async () => {
    setPhotoError(null);
    setSuccessMessage(null);
    setUploadingPhoto(true);
    try {
      const updated = await deleteProfilePhoto();
      setProfile(updated);
      setFormData(updated);
      if (onProfileUpdated) onProfileUpdated(updated);
      setSuccessMessage("Profile photo removed");
      setTimeout(() => setSuccessMessage(null), 3500);
    } catch (err: any) {
      setPhotoError(err.message || "Failed to remove profile photo");
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMessage(null);
    setErrorMessage(null);

    try {
      const updated = await updateUserProfile(formData);
      setProfile(updated);
      setFormData(updated);
      if (onProfileUpdated) onProfileUpdated(updated);
      setSuccessMessage("Profile changes saved successfully");
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err: any) {
      setErrorMessage("Unable to save profile changes. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const initials = profile.full_name
    ? profile.full_name
        .trim()
        .split(" ")
        .map((w) => w[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "AN";

  return (
    <div className="flex flex-col w-full gap-space-lg max-w-5xl mx-auto pb-16">
      {/* Top Breadcrumb & Status */}
      <div className="flex items-center justify-between text-xs text-secondary border-b border-surface-container-low pb-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onNavigate("dashboard")}
            className="text-outline-variant hover:text-primary transition-colors cursor-pointer"
          >
            Dashboard
          </button>
          <span className="text-outline-variant">/</span>
          <span className="text-on-surface font-semibold">User Profile</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="font-mono text-[11px] text-emerald-600 font-semibold uppercase">
            Active Node Verified // {profile.node_id || "Node #IND-WEST-01"}
          </span>
        </div>
      </div>

      {/* Notifications / Alerts */}
      {successMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 text-xs font-semibold flex items-center gap-2 animate-fade-in">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 text-xs font-semibold flex items-center gap-2 animate-fade-in">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* PROFILE Hero Card */}
      <div className="bg-surface-container-lowest rounded-xl border border-surface-container shadow-xs p-6 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6">
          {/* Profile Photo Block with Change Photo / Remove */}
          <div className="flex flex-col items-center gap-2.5 shrink-0">
            <div className="relative w-24 h-24 rounded-2xl bg-primary-container text-on-primary flex items-center justify-center font-bold shadow-md overflow-hidden border-2 border-surface-container">
              {profile.avatar_url ? (
                <img
                  src={profile.avatar_url}
                  alt={profile.full_name}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = "none";
                  }}
                />
              ) : (
                <span className="text-2xl font-mono tracking-wider">{initials}</span>
              )}
              {uploadingPhoto && (
                <div className="absolute inset-0 bg-black/60 flex items-center justify-center text-white">
                  <Loader2 className="w-6 h-6 animate-spin text-primary" />
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              <label
                htmlFor="photo-upload-input"
                className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-surface-container-low hover:bg-surface-container text-on-surface text-[11px] font-semibold border border-surface-container cursor-pointer transition-colors"
                title="Upload new profile picture"
              >
                <Camera className="w-3.5 h-3.5 text-primary" />
                <span>Change Photo</span>
                <input
                  id="photo-upload-input"
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={handlePhotoUpload}
                  disabled={uploadingPhoto}
                  className="hidden"
                />
              </label>

              {profile.avatar_url && (
                <button
                  type="button"
                  onClick={handlePhotoRemove}
                  disabled={uploadingPhoto}
                  className="p-1 rounded-md text-secondary hover:text-rose-500 hover:bg-rose-50 transition-colors cursor-pointer"
                  title="Remove custom photo"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {photoError && (
              <span className="text-[10px] text-rose-500 font-semibold text-center max-w-[180px]">
                {photoError}
              </span>
            )}
          </div>

          {/* Profile Overview */}
          <div className="flex flex-col gap-1 text-center sm:text-left">
            <div className="flex items-center justify-center sm:justify-start gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-on-surface tracking-tight">
                {profile.full_name}
              </h1>
              <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-primary/10 text-primary border border-primary/20">
                {profile.call_sign}
              </span>
            </div>
            <p className="text-xs text-secondary font-medium flex items-center justify-center sm:justify-start gap-1.5 mt-0.5">
              <span>{profile.title}</span>
              <span>•</span>
              <span className="text-on-surface">{profile.organization}</span>
            </p>
            <div className="flex items-center justify-center sm:justify-start gap-3 mt-2 text-[11px] text-outline-variant font-mono">
              <span className="flex items-center gap-1">
                <MapPin className="w-3 h-3 text-secondary" />
                {profile.station}
              </span>
              <span>|</span>
              <span className="flex items-center gap-1 text-emerald-600 font-semibold">
                <Shield className="w-3 h-3" />
                {profile.clearance_level}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Edit Form */}
      <form onSubmit={handleSave} className="flex flex-col gap-space-md">
        {/* Section 1: Personal Information */}
        <div className="p-6 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col gap-4">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-primary" />
              <h2 className="text-sm font-bold text-on-surface uppercase tracking-wider">
                Personal Information
              </h2>
            </div>
            <span className="text-[10px] font-mono uppercase text-secondary">Section 01</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-full-name" className="text-[11px] font-semibold text-secondary">
                Full Name
              </label>
              <input
                id="field-full-name"
                type="text"
                value={formData.full_name || ""}
                onChange={(e) => handleInputChange("full_name", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface font-semibold"
                placeholder="e.g. Cmdr. Rajesh K. Varma"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-email" className="text-[11px] font-semibold text-secondary flex items-center gap-1">
                <Mail className="w-3 h-3 text-secondary" />
                <span>Email</span>
              </label>
              <input
                id="field-email"
                type="email"
                value={formData.email || ""}
                onChange={(e) => handleInputChange("email", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface font-mono"
                placeholder="name@agency.gov"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-phone" className="text-[11px] font-semibold text-secondary flex items-center gap-1">
                <Phone className="w-3 h-3 text-secondary" />
                <span>Phone</span>
              </label>
              <input
                id="field-phone"
                type="text"
                value={formData.phone || ""}
                onChange={(e) => handleInputChange("phone", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface font-mono"
                placeholder="+91 (22) 2269-8000"
              />
            </div>
          </div>
        </div>

        {/* Section 2: Organization */}
        <div className="p-6 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col gap-4">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Building className="w-4 h-4 text-indigo-500" />
              <h2 className="text-sm font-bold text-on-surface uppercase tracking-wider">
                Organization
              </h2>
            </div>
            <span className="text-[10px] font-mono uppercase text-secondary">Section 02</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-organization" className="text-[11px] font-semibold text-secondary">
                Organization
              </label>
              <input
                id="field-organization"
                type="text"
                value={formData.organization || ""}
                onChange={(e) => handleInputChange("organization", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface"
                placeholder="DG Shipping / Indian Coast Guard"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-department" className="text-[11px] font-semibold text-secondary">
                Department
              </label>
              <input
                id="field-department"
                type="text"
                value={formData.department || ""}
                onChange={(e) => handleInputChange("department", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface"
                placeholder="Maritime Environmental Enforcement Division"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-job-title" className="text-[11px] font-semibold text-secondary">
                Job Title
              </label>
              <input
                id="field-job-title"
                type="text"
                value={formData.title || ""}
                onChange={(e) => handleInputChange("title", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface font-semibold"
                placeholder="Senior Marine Forensic Analyst"
                required
              />
            </div>
          </div>
        </div>

        {/* Section 3: Operational Profile */}
        <div className="p-6 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col gap-4">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Key className="w-4 h-4 text-amber-500" />
              <h2 className="text-sm font-bold text-on-surface uppercase tracking-wider">
                Operational Profile
              </h2>
            </div>
            <span className="text-[10px] font-mono uppercase text-secondary">Section 03</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-analyst-id" className="text-[11px] font-semibold text-secondary">
                Analyst ID
              </label>
              <input
                id="field-analyst-id"
                type="text"
                value={formData.call_sign || ""}
                onChange={(e) => handleInputChange("call_sign", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface font-mono font-bold"
                placeholder="CG-FOR-904"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-operational-region" className="text-[11px] font-semibold text-secondary">
                Operational Region
              </label>
              <input
                id="field-operational-region"
                type="text"
                value={formData.surveillance_sector || ""}
                onChange={(e) => handleInputChange("surveillance_sector", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface"
                placeholder="Exclusive Economic Zone (EEZ) — West Sector"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-assigned-node" className="text-[11px] font-semibold text-secondary">
                Assigned Node / Station
              </label>
              <input
                id="field-assigned-node"
                type="text"
                value={formData.station || ""}
                onChange={(e) => handleInputChange("station", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface"
                placeholder="Western Seaboard Command, Mumbai"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-specialization" className="text-[11px] font-semibold text-secondary">
                Specialization
              </label>
              <input
                id="field-specialization"
                type="text"
                value={formData.specialization || ""}
                onChange={(e) => handleInputChange("specialization", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface"
                placeholder="SAR Detection & Hydrodynamic Drift Reconstruction"
              />
            </div>
          </div>
        </div>

        {/* Section 4: Access */}
        <div className="p-6 rounded-xl bg-surface-container-lowest border border-surface-container shadow-xs flex flex-col gap-4">
          <div className="flex items-center justify-between pb-2 border-b border-surface-container-low">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-500" />
              <h2 className="text-sm font-bold text-on-surface uppercase tracking-wider">
                Access
              </h2>
            </div>
            <span className="text-[10px] font-mono uppercase text-secondary">Section 04</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-system-role" className="text-[11px] font-semibold text-secondary">
                System Role
              </label>
              <input
                id="field-system-role"
                type="text"
                value={formData.clearance_level || ""}
                onChange={(e) => handleInputChange("clearance_level", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface font-semibold"
                placeholder="Class-I Maritime Forensic Authority"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="field-access-level" className="text-[11px] font-semibold text-secondary">
                Access Level
              </label>
              <input
                id="field-access-level"
                type="text"
                value={formData.authorization_scope || ""}
                onChange={(e) => handleInputChange("authorization_scope", e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-container-low border border-surface-container focus:border-primary focus:outline-hidden text-xs text-on-surface"
                placeholder="MARPOL Annex I Enforcement & Legal Prosecution"
              />
            </div>
          </div>
        </div>

        {/* Submit Action Button */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-primary text-on-primary hover:bg-primary-hover font-semibold text-xs transition-colors shadow-sm cursor-pointer disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving Changes...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Save Changes</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

export default ProfilePage;
