using System;
using System.Collections.Generic;
using UnityEngine;

namespace TokenPet
{
    [Serializable]
    public sealed class TokenPetMotionProfile
    {
        public string id;
        public float duration = 1f;
        public float frequency = 1f;
        public float bob;
        public float sway;
        public float tilt;
        public float squash;
        public float stretch;
        public float smoothing = 0.08f;
    }

    [Serializable]
    internal sealed class TokenPetMotionProfileCatalog
    {
        public TokenPetMotionProfile[] profiles;
    }

    public sealed class TokenPetMotionProfiles
    {
        private readonly Dictionary<string, TokenPetMotionProfile> profiles =
            new(StringComparer.OrdinalIgnoreCase);

        private TokenPetMotionProfiles()
        {
        }

        public static TokenPetMotionProfiles Load()
        {
            TokenPetMotionProfiles library = new();
            TextAsset source = Resources.Load<TextAsset>("motion_profiles");
            if (source == null)
            {
                Debug.LogError("Missing Resources/motion_profiles.json");
                library.AddFallbackProfiles();
                return library;
            }

            TokenPetMotionProfileCatalog catalog =
                JsonUtility.FromJson<TokenPetMotionProfileCatalog>(source.text);
            if (catalog?.profiles != null)
            {
                foreach (TokenPetMotionProfile profile in catalog.profiles)
                {
                    if (profile != null && !string.IsNullOrWhiteSpace(profile.id))
                        library.profiles[profile.id] = profile;
                }
            }

            library.AddFallbackProfiles();
            return library;
        }

        public TokenPetMotionProfile Get(string id)
        {
            return profiles.TryGetValue(id, out TokenPetMotionProfile profile)
                ? profile
                : profiles["idle"];
        }

        private void AddFallbackProfiles()
        {
            AddFallback(new TokenPetMotionProfile
            {
                id = "idle", duration = 4.8f, frequency = 2.15f,
                bob = 0.035f, sway = 0.018f, tilt = 1.3f,
                squash = 0.024f, stretch = 0.020f, smoothing = 0.10f
            });
            AddFallback(new TokenPetMotionProfile
            {
                id = "walk", duration = 3.8f, frequency = 8.6f,
                bob = 0.10f, sway = 0.065f, tilt = 5.4f,
                squash = 0.050f, stretch = 0.045f, smoothing = 0.055f
            });
            AddFallback(new TokenPetMotionProfile
            {
                id = "poke", duration = 0.72f, frequency = 13f,
                bob = 0.24f, sway = 0.055f, tilt = 15f,
                squash = 0.16f, stretch = 0.13f, smoothing = 0.035f
            });
            AddFallback(new TokenPetMotionProfile
            {
                id = "drag", duration = 1f, frequency = 7f,
                bob = 0.025f, sway = 0.02f, tilt = 16f,
                squash = 0.08f, stretch = 0.13f, smoothing = 0.045f
            });
            AddFallback(new TokenPetMotionProfile
            {
                id = "airborne", duration = 1f, frequency = 10f,
                bob = 0.72f, sway = 0.20f, tilt = 280f,
                squash = 0.08f, stretch = 0.14f, smoothing = 0.025f
            });
            AddFallback(new TokenPetMotionProfile
            {
                id = "land", duration = 0.68f, frequency = 3f,
                bob = 0.06f, sway = 0f, tilt = 4f,
                squash = 0.34f, stretch = 0.28f, smoothing = 0.035f
            });
        }

        private void AddFallback(TokenPetMotionProfile profile)
        {
            if (!profiles.ContainsKey(profile.id))
                profiles[profile.id] = profile;
        }
    }
}
