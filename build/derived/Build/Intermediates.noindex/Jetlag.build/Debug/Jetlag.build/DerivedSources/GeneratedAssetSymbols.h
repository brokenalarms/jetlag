#import <Foundation/Foundation.h>

#if __has_attribute(swift_private)
#define AC_SWIFT_PRIVATE __attribute__((swift_private))
#else
#define AC_SWIFT_PRIVATE
#endif

/// The resource bundle ID.
static NSString * const ACBundleID AC_SWIFT_PRIVATE = @"com.daniellawrence.Jetlag";

/// The "AccentColor" asset catalog color resource.
static NSString * const ACColorNameAccentColor AC_SWIFT_PRIVATE = @"AccentColor";

/// The "NeonCyan" asset catalog color resource.
static NSString * const ACColorNameNeonCyan AC_SWIFT_PRIVATE = @"NeonCyan";

/// The "NeonPink" asset catalog color resource.
static NSString * const ACColorNameNeonPink AC_SWIFT_PRIVATE = @"NeonPink";

/// The "NeonPurple" asset catalog color resource.
static NSString * const ACColorNameNeonPurple AC_SWIFT_PRIVATE = @"NeonPurple";

/// The "NeonYellow" asset catalog color resource.
static NSString * const ACColorNameNeonYellow AC_SWIFT_PRIVATE = @"NeonYellow";

#undef AC_SWIFT_PRIVATE
