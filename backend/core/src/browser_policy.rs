//! Destination checks for a future isolated browser transport. No network I/O.
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use url::{Host, Url};

#[derive(Debug, PartialEq, Eq)]
pub enum DestinationError {
    InvalidUrl,
    OriginDenied,
    AddressDenied,
}

pub struct NavigationPolicy {
    origin: url::Origin,
}

impl NavigationPolicy {
    pub fn new(approved_origin: &str) -> Result<Self, DestinationError> {
        let url = parse(approved_origin)?;
        if url.path() != "/" || url.query().is_some() || url.fragment().is_some() {
            return Err(DestinationError::InvalidUrl);
        }
        Ok(Self {
            origin: url.origin(),
        })
    }

    pub fn destination(&self, value: &str) -> Result<Url, DestinationError> {
        let url = parse(value)?;
        if url.origin() != self.origin {
            return Err(DestinationError::OriginDenied);
        }
        Ok(url)
    }

    pub fn redirect(&self, current: &Url, location: &str) -> Result<Url, DestinationError> {
        self.destination(current.as_str())?;
        if location.len() > 4096
            || location.trim() != location
            || location
                .bytes()
                .any(|byte| byte.is_ascii_control() || byte == b'\\')
        {
            return Err(DestinationError::InvalidUrl);
        }
        let first_segment = location.split(['/', '?', '#']).next().unwrap_or_default();
        if first_segment.contains(':') {
            return self.destination(location);
        }
        let next = current
            .join(location)
            .map_err(|_| DestinationError::InvalidUrl)?;
        self.destination(next.as_str())
    }

    /// Check all DNS answers and the actual peer. A transport must dial only
    /// the checked addresses, with TLS verification for the original host.
    pub fn check_peer(&self, resolved: &[IpAddr], peer: IpAddr) -> Result<(), DestinationError> {
        if !resolved.contains(&peer) || !resolved.iter().copied().all(public_address) {
            return Err(DestinationError::AddressDenied);
        }
        Ok(())
    }
}

fn parse(value: &str) -> Result<Url, DestinationError> {
    if !value
        .get(..8)
        .is_some_and(|prefix| prefix.eq_ignore_ascii_case("https://"))
        || value.len() > 4096
        || value.trim() != value
        || value.bytes().any(|b| b.is_ascii_control() || b == b'\\')
    {
        return Err(DestinationError::InvalidUrl);
    }
    let url = Url::parse(value).map_err(|_| DestinationError::InvalidUrl)?;
    let host_allowed = matches!(url.host(), Some(Host::Domain(host)) if host.contains('.') && !host.ends_with('.') && !["local", "localhost", "internal", "test", "invalid", "onion", "example", "arpa"].contains(&host.rsplit('.').next().unwrap_or_default()));
    if url.scheme() != "https"
        || !url.username().is_empty()
        || url.password().is_some()
        || !host_allowed
    {
        return Err(DestinationError::InvalidUrl);
    }
    Ok(url)
}

fn public_address(address: IpAddr) -> bool {
    match address {
        IpAddr::V4(ip) => public_v4(ip),
        IpAddr::V6(ip) => public_v6(ip),
    }
}

fn public_v4(ip: Ipv4Addr) -> bool {
    !matches!(
        ip.octets(),
        [0 | 10 | 127 | 224..=255, ..]
            | [100, 64..=127, ..]
            | [169, 254, ..]
            | [172, 16..=31, ..]
            | [192, 0, 0 | 2, _]
            | [192, 88, 99, _]
            | [192, 168, ..]
            | [198, 18 | 19, ..]
            | [198, 51, 100, _]
            | [203, 0, 113, _]
    )
}

fn public_v6(ip: Ipv6Addr) -> bool {
    matches!(ip.segments(), [0x2000..=0x3fff, ..])
        && !matches!(
            ip.segments(),
            [0x2001, 0..=0x1ff | 0xdb8, ..] | [0x2002, ..] | [0x3fff, 0..=0xfff, ..]
        )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn navigation_and_redirect_require_the_exact_https_origin() {
        let policy = NavigationPolicy::new("https://EXAMPLE.com:443").unwrap();
        let start = policy.destination("https://example.com/a").unwrap();
        assert_eq!(policy.redirect(&start, "../b").unwrap().path(), "/b");
        for target in [
            "//other.example.com",
            "https://example.com:8443/",
            "http://example.com/",
            "https://u:p@example.com/",
            "https://127.1/",
            "file:///test",
            "https:example.com",
            " https://example.com/",
            "\\other.example.com",
        ] {
            assert!(policy.redirect(&start, target).is_err(), "{target}");
        }
        assert!(NavigationPolicy::new("https://example.com/path").is_err());
        assert!(NavigationPolicy::new("https://machine.local").is_err());
    }

    #[test]
    fn every_dns_answer_and_the_connected_peer_are_checked() {
        let policy = NavigationPolicy::new("https://example.com").unwrap();
        let public = "93.184.216.34".parse().unwrap();
        let public_v6 = "2606:4700::1111".parse().unwrap();
        assert!(policy.check_peer(&[public, public_v6], public_v6).is_ok());
        assert!(policy.check_peer(&[public], public_v6).is_err());
        for ip in [
            "127.0.0.1",
            "100.64.0.1",
            "169.254.169.254",
            "192.168.0.1",
            "::1",
            "::ffff:127.0.0.1",
            "fc00::1",
            "2002:7f00:1::",
            "2001:db8::1",
        ] {
            assert!(
                policy
                    .check_peer(&[public, ip.parse().unwrap()], public)
                    .is_err(),
                "{ip}"
            );
        }
    }
}
